from django.db import transaction
from django.core.cache import cache
from django.contrib.auth import get_user_model
from rest_framework import status, serializers
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from authflow.services import OTPManager, OTPInvalidError
from common.otp.service import MultiChannelOTPService
from payments.models import UserAccount
from accounts.services.security_guards import (
    validate_pin_format,
    is_pin_locked,
    record_failed_pin_attempt,
    clear_pin_attempts,
    set_security_cooldown,
    is_security_cooldown_active,
)
from common.phone.utils import get_phone_number

User = get_user_model()


def verify_actor_intent(user, request) -> tuple[bool, Response | None]:
    """
    Verifies user's authorization to make critical account updates:
    1. If user has usable password, check 'password'.
    2. If user has transaction PIN configured, check 'transaction_pin'.
    3. If user is an OAuth/passwordless user without PIN, verify via 'auth_otp_code'
       sent to their currently registered email (or phone).
    """
    req_data = getattr(request, "data", None)
    if req_data is None:
        import json
        body = getattr(request, "body", None)
        if body:
            try:
                req_data = json.loads(body.decode("utf-8"))
            except Exception:
                req_data = getattr(request, "POST", None) or {}
        else:
            req_data = getattr(request, "POST", None) or {}
    password = req_data.get("password")
    pin = req_data.get("transaction_pin")
    auth_otp = req_data.get("auth_otp_code")

    if user.has_usable_password():
        if not password or not user.check_password(password):
            return False, Response({"error": "Invalid current password."}, status=status.HTTP_401_UNAUTHORIZED)
        return True, None

    payment_account = getattr(user, "payment_account", None)
    if payment_account and payment_account.has_transaction_pin:
        if not pin or not payment_account.check_transaction_pin(str(pin)):
            return False, Response({"error": "Valid transaction_pin is required."}, status=status.HTTP_401_UNAUTHORIZED)
        return True, None

    # OAuth / passwordless user without PIN: authenticate via current email or phone OTP
    current_identifier = user.email or user.phone_number
    if not current_identifier:
        return False, Response({"error": "Account has no verified email or phone to authorize changes."}, status=status.HTTP_400_BAD_REQUEST)

    if not auth_otp:
        channel = "email" if user.email else "phone"
        try:
            OTPManager.send(channel=channel, identifier=current_identifier)
        except Exception as exc:
            return False, Response({"error": f"Failed to send authorization code: {str(exc)}"}, status=status.HTTP_400_BAD_REQUEST)
        return False, Response(
            {
                "status": "auth_otp_required",
                "message": f"Authorization code sent to your registered {channel} ({current_identifier}). Include 'auth_otp_code' to confirm.",
            },
            status=status.HTTP_202_ACCEPTED,
        )

    try:
        verified_id = OTPManager.verify(otp_code=auth_otp)
        if str(verified_id).strip().lower() != str(current_identifier).strip().lower():
            return False, Response({"error": "Authorization code does not match registered account."}, status=status.HTTP_400_BAD_REQUEST)
    except OTPInvalidError as e:
        return False, Response({"error": f"Invalid authorization code: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

    return True, None


# ─────────────────────────────────────────────────────────────────────────────
# 1. PHONE NUMBER 2-STEP GUARDED FLOW
# ─────────────────────────────────────────────────────────────────────────────

class RequestChangePhoneView(APIView):
    """
    POST /api/accounts/security/change-phone/request/
    Step 1: Authenticate with password, PIN, or current email OTP, supply new phone number, receive OTP.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        new_phone = request.data.get("new_phone_number")

        if not new_phone:
            return Response({"error": "new_phone_number is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Authenticate intent
        ok, err_resp = verify_actor_intent(user, request)
        if not ok:
            return err_resp

        # Check collision
        if User.objects.exclude(id=user.id).filter(phone_number=new_phone).exists():
            return Response({"error": "This phone number is already registered to another account."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            OTPManager.send(channel="phone", identifier=new_phone)
        except Exception as e:
            return Response({"error": f"Failed to send verification code: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        cache.set(f"pending_phone_change:{user.id}", str(new_phone).strip(), timeout=900)
        return Response({"message": f"Verification code sent to {new_phone}."})


class ConfirmChangePhoneView(APIView):
    """
    POST /api/accounts/security/change-phone/confirm/
    Step 2: Submit OTP received on the new phone number to complete the update.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        new_phone = request.data.get("new_phone_number")
        otp_code = request.data.get("otp_code")

        if not new_phone or not otp_code:
            return Response({"error": "new_phone_number and otp_code are required."}, status=status.HTTP_400_BAD_REQUEST)

        pending_phone = cache.get(f"pending_phone_change:{user.id}")
        if pending_phone is not None and str(pending_phone).strip() != str(new_phone).strip():
            return Response(
                {"error": "Phone number does not match the authorized phone change request."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if pending_phone is None:
            ok, err_resp = verify_actor_intent(user, request)
            if not ok:
                return Response(
                    {"error": "No active phone change request found. Please initiate step 1 (/change-phone/request/) first."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        try:
            verified_id = OTPManager.verify(otp_code=otp_code)
        except OTPInvalidError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        if str(verified_id).strip() != str(new_phone).strip():
            return Response({"error": "Verification code does not match the provided phone number."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            if User.objects.exclude(id=user.id).filter(phone_number=new_phone).exists():
                return Response({"error": "This phone number is already registered to another account."}, status=status.HTTP_400_BAD_REQUEST)
            user.phone_number = new_phone
            user.save(update_fields=["phone_number"])
            cache.delete(f"pending_phone_change:{user.id}")
            set_security_cooldown(user, hours=24)

        return Response({"message": "Phone number updated successfully. 24-hour security cooldown applied to withdrawals."})


# ─────────────────────────────────────────────────────────────────────────────
# 2. EMAIL 2-STEP GUARDED FLOW
# ─────────────────────────────────────────────────────────────────────────────

class RequestChangeEmailView(APIView):
    """
    POST /api/accounts/security/change-email/request/
    Step 1: Authenticate with password or current PIN, supply new email, receive OTP.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        new_email = request.data.get("new_email")
        password = request.data.get("password")

        if not new_email:
            return Response({"error": "new_email is required."}, status=status.HTTP_400_BAD_REQUEST)

        new_email = new_email.strip().lower()

        # Authenticate intent
        ok, err_resp = verify_actor_intent(user, request)
        if not ok:
            return err_resp

        if User.objects.exclude(id=user.id).filter(email__iexact=new_email).exists():
            return Response({"error": "This email is already registered to another account."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            OTPManager.send(channel="email", identifier=new_email)
        except Exception as e:
            return Response({"error": f"Failed to send verification code: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        cache.set(f"pending_email_change:{user.id}", new_email, timeout=900)
        return Response({"message": f"Verification code sent to {new_email}."})


class ConfirmChangeEmailView(APIView):
    """
    POST /api/accounts/security/change-email/confirm/
    Step 2: Submit OTP received on the new email to complete the update.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        new_email = request.data.get("new_email")
        otp_code = request.data.get("otp_code")

        if not new_email or not otp_code:
            return Response({"error": "new_email and otp_code are required."}, status=status.HTTP_400_BAD_REQUEST)

        new_email = new_email.strip().lower()

        pending_email = cache.get(f"pending_email_change:{user.id}")
        if pending_email is not None and str(pending_email).strip().lower() != new_email:
            return Response(
                {"error": "Email does not match the authorized email change request."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if pending_email is None:
            ok, err_resp = verify_actor_intent(user, request)
            if not ok:
                return Response(
                    {"error": "No active email change request found. Please initiate step 1 (/change-email/request/) first."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        try:
            verified_id = OTPManager.verify(otp_code=otp_code)
        except OTPInvalidError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        if str(verified_id).strip().lower() != new_email:
            return Response({"error": "Verification code does not match the provided email."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            if User.objects.exclude(id=user.id).filter(email__iexact=new_email).exists():
                return Response({"error": "This email is already registered to another account."}, status=status.HTTP_400_BAD_REQUEST)
            user.email = new_email
            user.save(update_fields=["email"])
            cache.delete(f"pending_email_change:{user.id}")
            set_security_cooldown(user, hours=24)

        return Response({"message": "Email updated successfully. 24-hour security cooldown applied to withdrawals."})


# ─────────────────────────────────────────────────────────────────────────────
# 3. TRANSACTION PIN FULL CRUD FOR CUSTOMER / USER ACCOUNT
# ─────────────────────────────────────────────────────────────────────────────

class CustomerPinStatusView(APIView):
    """
    GET /api/customer/pin/status/
    Returns whether PIN is set, lock status, and cooldown status.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        account = getattr(user, "payment_account", None)
        has_pin = bool(account and account.has_transaction_pin)

        locked, remaining_lock = is_pin_locked(user.id)
        cooldown_active, remaining_cooldown = is_security_cooldown_active(user)

        return Response({
            "has_pin": has_pin,
            "is_locked": locked,
            "lockout_remaining_seconds": remaining_lock,
            "withdrawal_cooldown_active": cooldown_active,
            "cooldown_remaining_seconds": remaining_cooldown,
        })


class CustomerSetPinView(APIView):
    """
    POST /api/customer/pin/set/
    Initial creation of a 4-digit transaction PIN.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        if hasattr(user, "business_admin") or hasattr(user, "driver_profile"):
            return Response(
                {"error": "This endpoint is restricted to customer accounts. Business administrators and drivers manage credentials in their dedicated portals."},
                status=status.HTTP_403_FORBIDDEN,
            )

        account, _ = UserAccount.objects.get_or_create(user=user)

        if account.has_transaction_pin:
            return Response({"error": "PIN is already set. Use change-pin to update it."}, status=status.HTTP_400_BAD_REQUEST)

        pin = request.data.get("pin")
        confirm_pin = request.data.get("confirm_pin")

        if not pin or not confirm_pin:
            return Response({"error": "pin and confirm_pin are required."}, status=status.HTTP_400_BAD_REQUEST)

        if str(pin) != str(confirm_pin):
            return Response({"error": "PINs do not match."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_pin_format(pin)
        except serializers.ValidationError as e:
            return Response({"error": e.detail[0] if isinstance(e.detail, list) else str(e.detail)}, status=status.HTTP_400_BAD_REQUEST)

        account.set_transaction_pin(str(pin))
        account.save(update_fields=["transaction_pin_hash"])
        clear_pin_attempts(user.id)

        return Response({"message": "Transaction PIN created successfully."}, status=status.HTTP_201_CREATED)


class CustomerChangePinView(APIView):
    """
    PUT /api/customer/pin/change/
    Change an existing transaction PIN using current PIN.
    """
    permission_classes = [IsAuthenticated]

    def put(self, request):
        user = request.user
        if hasattr(user, "business_admin") or hasattr(user, "driver_profile"):
            return Response(
                {"error": "This endpoint is restricted to customer accounts. Business administrators and drivers manage credentials in their dedicated portals."},
                status=status.HTTP_403_FORBIDDEN,
            )

        locked, rem = is_pin_locked(user.id)
        if locked:
            return Response({"error": f"PIN is temporarily locked due to failed attempts. Try again in {rem // 60} minutes."}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        account = getattr(user, "payment_account", None)
        if not account or not account.has_transaction_pin:
            return Response({"error": "No PIN set yet. Use set-pin first."}, status=status.HTTP_400_BAD_REQUEST)

        current_pin = request.data.get("current_pin")
        new_pin = request.data.get("new_pin")
        confirm_pin = request.data.get("confirm_pin")

        if not current_pin or not new_pin or not confirm_pin:
            return Response({"error": "current_pin, new_pin, and confirm_pin are required."}, status=status.HTTP_400_BAD_REQUEST)

        if not account.check_transaction_pin(str(current_pin)):
            attempts = record_failed_pin_attempt(user.id, ip_address=request.META.get("REMOTE_ADDR"))
            remaining = max(0, 5 - attempts)
            return Response({"error": f"Incorrect current PIN. {remaining} attempt(s) remaining."}, status=status.HTTP_400_BAD_REQUEST)

        if str(new_pin) != str(confirm_pin):
            return Response({"error": "New PINs do not match."}, status=status.HTTP_400_BAD_REQUEST)

        if str(new_pin) == str(current_pin):
            return Response({"error": "New PIN cannot be identical to current PIN."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_pin_format(new_pin)
        except serializers.ValidationError as e:
            return Response({"error": e.detail[0] if isinstance(e.detail, list) else str(e.detail)}, status=status.HTTP_400_BAD_REQUEST)

        account.set_transaction_pin(str(new_pin))
        account.save(update_fields=["transaction_pin_hash"])
        clear_pin_attempts(user.id)
        set_security_cooldown(user, hours=24, reason="Transaction PIN changed", ip_address=request.META.get("REMOTE_ADDR"))

        return Response({"message": "Transaction PIN updated successfully. 24-hour security cooldown applied to withdrawals."})


class CustomerResetPinRequestView(APIView):
    """
    POST /api/customer/pin/reset/request/
    Step 1 of PIN reset: Send OTP to customer's registered phone or email, with SMS-to-email fallback.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        if hasattr(user, "business_admin") or hasattr(user, "driver_profile"):
            return Response(
                {"error": "This endpoint is restricted to customer accounts. Business administrators and drivers manage credentials in their dedicated portals."},
                status=status.HTTP_403_FORBIDDEN,
            )

        channel = request.data.get("channel", "phone")

        if channel not in ("phone", "email"):
            return Response({"error": "Channel must be 'phone' or 'email'."}, status=status.HTTP_400_BAD_REQUEST)

        phone_num = get_phone_number(user)
        email_addr = (user.email or "").strip().lower()

        if channel == "email" and not email_addr:
            return Response({"error": "No registered email found for this account."}, status=status.HTTP_400_BAD_REQUEST)

        if channel == "phone" and not phone_num and not email_addr:
            return Response({"error": "No registered phone number or email found for this account."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            prefer_email = (channel == "email")
            delivery = MultiChannelOTPService.send_with_fallback(
                phone_number=phone_num,
                email=email_addr,
                prefer_email=prefer_email,
            )
        except Exception as e:
            return Response({"error": f"Failed to send reset code: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        if delivery.get("fallback"):
            return Response({"message": "Verification code sent to your registered email (SMS delivery fallback)."})

        return Response({"message": f"PIN reset verification code sent to your registered {delivery.get('channel_used')}."})


class CustomerResetPinConfirmView(APIView):
    """
    POST /api/customer/pin/reset/confirm/
    Step 2 of PIN reset: Verify OTP and set new transaction PIN.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        if hasattr(user, "business_admin") or hasattr(user, "driver_profile"):
            return Response(
                {"error": "This endpoint is restricted to customer accounts. Business administrators and drivers manage credentials in their dedicated portals."},
                status=status.HTTP_403_FORBIDDEN,
            )

        otp_code = request.data.get("otp_code")
        new_pin = request.data.get("new_pin")
        confirm_pin = request.data.get("confirm_pin")

        if not otp_code or not new_pin or not confirm_pin:
            return Response({"error": "otp_code, new_pin, and confirm_pin are required."}, status=status.HTTP_400_BAD_REQUEST)

        if str(new_pin) != str(confirm_pin):
            return Response({"error": "New PINs do not match."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_pin_format(new_pin)
        except serializers.ValidationError as e:
            return Response({"error": e.detail[0] if isinstance(e.detail, list) else str(e.detail)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            verified_id = OTPManager.verify(otp_code=otp_code)
        except OTPInvalidError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # Confirm identity matches this user
        user_phone = get_phone_number(user.phone_number)
        user_email = (user.email or "").strip().lower()
        verified_str = str(verified_id).strip()

        if verified_str != user_phone and verified_str.lower() != user_email:
            return Response({"error": "Verification code does not belong to this account."}, status=status.HTTP_403_FORBIDDEN)

        account, _ = UserAccount.objects.get_or_create(user=user)
        account.set_transaction_pin(str(new_pin))
        account.save(update_fields=["transaction_pin_hash"])

        clear_pin_attempts(user.id)
        set_security_cooldown(user, hours=24, reason="Transaction PIN reset via OTP", ip_address=request.META.get("REMOTE_ADDR"))

        return Response({"message": "Transaction PIN reset successfully. 24-hour security cooldown applied to withdrawals."})


# ─────────────────────────────────────────────────────────────────────────────
# 4. INITIAL PASSWORD SETUP FOR OAUTH / PASSWORDLESS USERS
# ─────────────────────────────────────────────────────────────────────────────

class SetPasswordView(APIView):
    """
    POST /api/accounts/security/set-password/
    Allows OAuth or passwordless users (who currently have no password set)
    to establish an initial account password.
    Requires actor intent verification (via current PIN or current email OTP).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        if user.has_usable_password():
            return Response(
                {"error": "Password already configured. Use the change password endpoint instead."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        new_password = request.data.get("new_password")
        if not new_password or len(str(new_password)) < 8:
            return Response(
                {"error": "new_password is required and must be at least 8 characters."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ok, err_resp = verify_actor_intent(user, request)
        if not ok:
            return err_resp

        user.set_password(str(new_password))
        user.save(update_fields=["password"])
        set_security_cooldown(user, hours=24, reason="Initial password configured", ip_address=request.META.get("REMOTE_ADDR"))

        return Response({"message": "Password configured successfully. 24-hour security cooldown applied to withdrawals."})
