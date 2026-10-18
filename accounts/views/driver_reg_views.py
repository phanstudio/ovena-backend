import base64
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import GenericAPIView

from accounts.models import (
    DriverProfile, DriverCred, DriverAvailability, User,
    DriverDocument, DriverBankAccount, DriverOnboardingSubmission, DriverVerification,
)
from accounts.serializers import (
    OnboardingPhase1InputSerializer, OnboardingPhase1OutputSerializer,
    OnboardingPhase2InputSerializer, OnboardingPhase2OutputSerializer,
    OnboardingPhase3InputSerializer, OnboardingPhase3OutputSerializer,
    OnboardingPhase4InputSerializer, OnboardingPhase4OutputSerializer,
    OnboardingStatusOutputSerializer,
)
from payments.models import Bank
from payments.integrations import client
from verification import service as verification_service
from referrals.services import apply_referral_code
from drf_spectacular.utils import extend_schema # type: ignore
from authflow.services.phone_number import get_phone_number
from authflow.services.jwt import issue_jwt_for_user_with_plan
from accounts.services.profiles import (
    PROFILE_DRIVER,
)

# transaction atomics.

def _get_or_create_submission(profile: DriverProfile) -> DriverOnboardingSubmission:
    """Always work against the latest non-approved/non-rejected submission."""
    submission = (
        DriverOnboardingSubmission.objects
        .filter(driver=profile)
        .exclude(status__in=[
            DriverOnboardingSubmission.STATUS_APPROVED,
            DriverOnboardingSubmission.STATUS_REJECTED,
        ])
        .order_by("-created_at")
        .first()
    )
    if not submission:
        last_rejected = (
            DriverOnboardingSubmission.objects
            .filter(driver=profile, status=DriverOnboardingSubmission.STATUS_REJECTED)
            .order_by("-created_at")
            .first()
        )
        inherited_answers = dict(last_rejected.answers) if last_rejected and last_rejected.answers else {}
        submission = DriverOnboardingSubmission.objects.create(
            driver=profile,
            status=DriverOnboardingSubmission.STATUS_DRAFT,
            answers=inherited_answers,
        )
    return submission


def _phases_complete(submission: DriverOnboardingSubmission) -> list[int]:
    answers = submission.answers or {}
    complete = []
    if answers.get("phase_1_complete"):
        complete.append(1)
    if answers.get("phase_2_complete"):
        complete.append(2)
    if answers.get("phase_3_complete"):
        complete.append(3)
    if answers.get("phase_4_complete"):
        complete.append(4)
    return complete


def _current_phase(complete: list[int]) -> int:
    for p in [1, 2, 3, 4]:
        if p not in complete:
            return p
    return 4


def _guard_submitted(submission: DriverOnboardingSubmission, response_on_fail):
    """Returns an error Response if the submission is already submitted/approved/rejected."""
    if submission.status == DriverOnboardingSubmission.STATUS_SUBMITTED:
        return Response(
            {"detail": "Onboarding is already submitted and awaiting review. Contact support to make changes."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return None


def _ref_from(result: dict) -> str:
    """Best-effort pull of a provider reference out of a verification.service result."""
    data = result.get("data")
    if not isinstance(data, dict):
        return ""
    for key in ("reference", "tracking_id", "entity_id", "id"):
        if data.get(key):
            return str(data[key])
    return ""


def _guard_already_approved(profile: DriverProfile):
    """
    Blocks phase PUTs once this driver has already been approved.

    Without this, _get_or_create_submission() would never even see the
    problem: it explicitly EXCLUDES approved/rejected submissions when
    looking for an "in progress" one, so for an already-approved driver
    it finds nothing and happily creates a brand new DRAFT submission -
    which sails straight past _guard_submitted() (that only checks for
    STATUS_SUBMITTED) and lets every phase view overwrite profile data,
    bank details, vehicle info, even the account password (Phase 1 is
    AllowAny) with no re-review at all. This has to run BEFORE
    _get_or_create_submission() is called, using the true latest
    submission, not the filtered one.
    """
    latest = (
        DriverOnboardingSubmission.objects
        .filter(driver=profile)
        .order_by("-created_at")
        .first()
    )
    if latest and latest.status == DriverOnboardingSubmission.STATUS_APPROVED:
        return Response(
            {"detail": "Your onboarding has already been approved. Contact support to update your details."},
            status=status.HTTP_403_FORBIDDEN,
        )
    return None


# ─── Status ───────────────────────────────────────────────────────────────────

@extend_schema(
    responses=OnboardingStatusOutputSerializer,
)
class OnboardingStatusView(APIView):
    """
    GET /onboarding/status/
    Returns the driver's overall onboarding progress.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = get_object_or_404(DriverProfile, user=request.user)
        latest = (
            DriverOnboardingSubmission.objects
            .filter(driver=profile)
            .order_by("-created_at")
            .first()
        )
        if latest and latest.status in [
            DriverOnboardingSubmission.STATUS_REJECTED,
            DriverOnboardingSubmission.STATUS_APPROVED,
            DriverOnboardingSubmission.STATUS_SUBMITTED,
        ]:
            submission = latest
        else:
            submission = _get_or_create_submission(profile)

        complete = _phases_complete(submission)
        answers = submission.answers or {}

        out = {
            "current_phase": _current_phase(complete),
            "phases_complete": complete,
            "all_phases_complete": len(complete) == 4,
            "submission_status": submission.status,
            "reviewer_note": submission.reviewer_note or "",
            "can_retry": submission.status == DriverOnboardingSubmission.STATUS_REJECTED,
            "phase_data": {
                "phase_1": answers.get("phase_1"),
                "phase_2": answers.get("phase_2"),
                "phase_3": answers.get("phase_3"),
                "phase_4": answers.get("phase_4"),
            },
        }
        return Response(OnboardingStatusOutputSerializer(out).data)


class OnboardingPhase1View(GenericAPIView):
    """
    PUT /onboarding/phase/1/
    Saves personal info, contact details, and next-of-kin.
    Driver can re-submit to update until final submission.
    """
    permission_classes = [AllowAny]
    serializer_class = OnboardingPhase1InputSerializer

    def put(self, request):
        user, _ = User.objects.get_or_create(email=request.data["email"])
        serializer = self.get_serializer(
            data=request.data,
            context={"driver_user_id": user.pk},
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        profile, _ = DriverProfile.objects.get_or_create(user=user)

        guard = _guard_already_approved(profile)
        if guard:
            return guard

        submission = _get_or_create_submission(profile)

        guard = _guard_submitted(submission, None)
        if guard:
            return guard        

        # ── Persist to DriverProfile ──
        profile.first_name = data["first_name"]
        profile.last_name = data["last_name"]
        profile.gender = data["gender"]
        profile.birth_date = data["birth_date"]
        profile.residential_address = data["residential_address"]
        profile.save(update_fields=["first_name", "last_name", "gender", "birth_date", "residential_address"])

        # ── Persist to User ──
        user.phone_number = data["phone_number"]
        user.email = data["email"]
        user.set_password(data["password"])
        user.save(update_fields=["phone_number", "email", "password"])
        token = issue_jwt_for_user_with_plan(user, active_profile=PROFILE_DRIVER)

        # ── Persist next-of-kin to DriverCred ──
        cred, _ = DriverCred.objects.get_or_create(user=profile)
        cred.next_of_kin_name = data["next_of_kin_name"]
        cred.next_of_kin_phone = data["next_of_kin_phone"]
        cred.save(update_fields=["next_of_kin_name", "next_of_kin_phone"])

        referre_code = data.get("referre_code", "")
        if referre_code:
            try:
                device_id = request.headers.get("X-Device-ID")
                ip_address = request.META.get("REMOTE_ADDR")
                apply_referral_code(
                    user=profile.user,
                    profile=profile,
                    code=referre_code,
                    role="driver",
                    device_id=device_id,
                    ip_address=ip_address,
                )
            except DjangoValidationError as exc:
                msg = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
                return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

        # ── Snapshot into submission answers ──
        answers = submission.answers or {}
        answers["phase_1"] = {
            "first_name": data["first_name"],
            "last_name": data["last_name"],
            "phone_number": get_phone_number(data["phone_number"]),
            "email": data["email"],
            "gender": data["gender"],
            "birth_date": str(data["birth_date"]),
            "residential_address": data["residential_address"],
            "next_of_kin_name": data["next_of_kin_name"],
            "next_of_kin_phone": get_phone_number(data["next_of_kin_phone"]),
            "next_of_kin_address": data["next_of_kin_address"],
        }
        answers["phase_1_complete"] = True
        submission.answers = answers
        submission.updated_at = timezone.now()
        submission.save(update_fields=["answers", "updated_at"])

        out = {
            "phase": 1,
            "status": "saved",
            "refresh": token["refresh"],
            "access": token["access"],
            **answers["phase_1"],
        }
        return Response(OnboardingPhase1OutputSerializer(out).data)


class OnboardingPhase2View(GenericAPIView):
    """
    PUT /onboarding/phase/2/
    Saves driver's license image, NIN/BVN (verified via Mono),
    vehicle info, and guarantor details.
    Phase 1 must be complete.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = OnboardingPhase2InputSerializer

    def put(self, request):
        profile = get_object_or_404(DriverProfile, user=request.user)

        guard = _guard_already_approved(profile)
        if guard:
            return guard

        submission = _get_or_create_submission(profile)

        guard = _guard_submitted(submission, None)
        if guard:
            return guard

        answers = submission.answers or {}
        if not answers.get("phase_1_complete"):
            return Response(
                {"detail": "Complete Phase 1 before proceeding."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # ── Driver's license document ──
        license_doc, _ = DriverDocument.objects.get_or_create(
            driver=profile,
            doc_type="drivers_license",
        )
        license_doc.file = data["drivers_license"]
        license_doc.status = DriverDocument.STATUS_PENDING
        license_doc.save(update_fields=["file", "status"])

        # ── Verified selfie document ──
        selfie_doc, _ = DriverDocument.objects.get_or_create(
            driver=profile,
            doc_type=DriverDocument.DOC_SELFIE,
        )
        selfie_doc.file = data["verified_selfie"]
        selfie_doc.status = DriverDocument.STATUS_PENDING
        selfie_doc.save(update_fields=["file", "status"])

        # ── NIN verification: Dojah first, Mono fallback ──
        nin_result = verification_service.verify_nin(data["nin"])
        nin_ver, _ = DriverVerification.objects.update_or_create(
            driver=profile,
            verification_type=DriverVerification.TYPE_NIN,
            defaults={
                "status": DriverVerification.STATUS_SUCCESS if nin_result["success"] else DriverVerification.STATUS_FAILED,
                "provider_name": nin_result["provider"] or "",
                "provider_ref": _ref_from(nin_result),
                "request_payload": {"nin": data["nin"][-4:].zfill(11)},  # store masked
                "response_payload": nin_result["data"] if nin_result["success"] else {"attempts": nin_result["attempts"]},
                "completed_at": timezone.now(),
            }
        )

        # ── BVN verification: Dojah only (Mono's BVN product needs an
        #    OTP round-trip with the driver, not a silent fallback here) ──
        bvn_result = verification_service.verify_bvn(data["bvn"])
        bvn_ver, _ = DriverVerification.objects.update_or_create(
            driver=profile,
            verification_type=DriverVerification.TYPE_BVN,
            defaults={
                "status": DriverVerification.STATUS_SUCCESS if bvn_result["success"] else DriverVerification.STATUS_FAILED,
                "provider_name": bvn_result["provider"] or "",
                "provider_ref": _ref_from(bvn_result),
                "request_payload": {"bvn": data["bvn"][-4:].zfill(11)},  # store masked
                "response_payload": bvn_result["data"] if bvn_result["success"] else {"attempts": bvn_result["attempts"]},
                "completed_at": timezone.now(),
            }
        )

        # ── Face match: selfie vs BVN/NIN registry photo (Dojah) ──
        data["verified_selfie"].seek(0)
        selfie_b64 = base64.b64encode(data["verified_selfie"].read()).decode("utf-8")
        face_result = verification_service.match_face_to_name(
            image=selfie_b64,
            first_name=profile.first_name,
            last_name=profile.last_name,
            bvn=data["bvn"],
            nin=data["nin"],
        )

        face_ver, _ = DriverVerification.objects.update_or_create(
            driver=profile,
            verification_type=DriverVerification.TYPE_FACE_MATCH,
            defaults={
                "status": DriverVerification.STATUS_SUCCESS if face_result["success"] else DriverVerification.STATUS_FAILED,
                "provider_name": face_result["provider"] or "",
                "provider_ref": _ref_from(face_result),
                "request_payload": {"first_name": profile.first_name, "last_name": profile.last_name},
                "response_payload": face_result["data"] if face_result["success"] else {"attempts": face_result["attempts"]},
                "completed_at": timezone.now(),
            },
        )

        # ── Store last4 in DriverCred ──
        cred, _ = DriverCred.objects.get_or_create(user=profile)
        cred.nin_last4 = data["nin"][-4:]
        cred.bvn_last4 = data["bvn"][-4:]
        cred.guarantor1_name = data["guarantor1_name"]
        cred.guarantor1_phone = data["guarantor1_phone"]
        cred.guarantor2_name = data["guarantor2_name"]
        cred.guarantor2_phone = data["guarantor2_phone"]
        cred.save(update_fields=[
            "nin_last4", "bvn_last4",
            "guarantor1_name", "guarantor1_phone",
            "guarantor2_name", "guarantor2_phone",
        ])

        # ── Vehicle info on DriverProfile ──
        profile.vehicle_type = data["vehicle_type"]
        profile.vehicle_make = data["vehicle_make"]
        profile.vehicle_number = data["plate_number"]
        profile.save(update_fields=["vehicle_type", "vehicle_make", "vehicle_number"])

        # ── Snapshot ──
        answers["phase_2"] = {
            "drivers_license_url": license_doc.file.url if license_doc.file else "",
            "selfie_url": selfie_doc.file.url if selfie_doc.file else "",
            "nin_last4": data["nin"][-4:],
            "bvn_last4": data["bvn"][-4:],
            "nin_verification_status": nin_ver.status,
            "bvn_verification_status": bvn_ver.status,
            "face_match_status": "verified" if face_result["success"] else "failed",
            "vehicle_type": data["vehicle_type"],
            "vehicle_make": data["vehicle_make"],
            "plate_number": data["plate_number"],
            "guarantor1_name": data["guarantor1_name"],
            "guarantor1_phone": data["guarantor1_phone"],
            "guarantor2_name": data["guarantor2_name"],
            "guarantor2_phone": data["guarantor2_phone"],
        }
        answers["phase_2_complete"] = True
        submission.answers = answers
        submission.updated_at = timezone.now()
        submission.save(update_fields=["answers", "updated_at"])

        out = {"phase": 2, "status": "saved", **answers["phase_2"]}
        return Response(OnboardingPhase2OutputSerializer(out).data)


# ─── Phase 3 — Availability, Compliance & Delivery Bag ───────────────────────

class OnboardingPhase3View(GenericAPIView):
    """
    PUT /onboarding/phase/3/
    Saves availability schedule, compliance Q&A, and delivery bag photo.
    Phase 2 must be complete.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = OnboardingPhase3InputSerializer

    def put(self, request):
        profile = get_object_or_404(DriverProfile, user=request.user)

        guard = _guard_already_approved(profile)
        if guard:
            return guard

        submission = _get_or_create_submission(profile)

        guard = _guard_submitted(submission, None)
        if guard:
            return guard

        answers = submission.answers or {}
        if not answers.get("phase_2_complete"):
            return Response(
                {"detail": "Complete Phase 2 before proceeding."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(data=request.data)
        # OnboardingPhase3InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # ── Availability slots ──
        # Replace all existing slots for this driver
        DriverAvailability.objects.filter(driver=profile).delete()
        for slot in data["availability"]:
            DriverAvailability.objects.create(
                driver=profile,
                weekday=slot["weekday"],
                time_mask=slot["time_mask"],
            )

        # ── Delivery bag document ──
        bag_doc, _ = DriverDocument.objects.get_or_create(
            driver=profile,
            doc_type=DriverDocument.DOC_DELIVERY_BAG,
        )
        bag_doc.file = data["delivery_bag"]
        bag_doc.status = DriverDocument.STATUS_PENDING
        bag_doc.save(update_fields=["file", "status"])

        # ── Snapshot ──
        answers["phase_3"] = {
            "availability": data["availability"],
            "compliance_answers": data["compliance_answers"],
            "delivery_bag_url": bag_doc.file.url if bag_doc.file else "",
        }
        answers["phase_3_complete"] = True
        # Store compliance in submission answers too for admin review
        answers["compliance"] = data["compliance_answers"]
        submission.answers = answers
        submission.updated_at = timezone.now()
        submission.save(update_fields=["answers", "updated_at"])

        out = {
            "phase": 3,
            "status": "saved",
            "availability": data["availability"],
            "compliance_answers": data["compliance_answers"],
            "delivery_bag_url": answers["phase_3"]["delivery_bag_url"],
        }
        return Response(OnboardingPhase3OutputSerializer(out).data)


# ─── Phase 4 — Bank Account & Selfie ─────────────────────────────────────────

class OnboardingPhase4View(GenericAPIView):
    """
    PUT /onboarding/phase/4/
    Saves bank account (verified via Paystack) and verified selfie.
    Phase 3 must be complete.
    Completing this phase marks onboarding as fully drafted — admin pulls for review.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = OnboardingPhase4InputSerializer

    def put(self, request):
        profile = get_object_or_404(DriverProfile, user=request.user)

        guard = _guard_already_approved(profile)
        if guard:
            return guard

        submission = _get_or_create_submission(profile)

        guard = _guard_submitted(submission, None)
        if guard:
            return guard

        answers = submission.answers or {}
        if not answers.get("phase_3_complete"):
            return Response(
                {"detail": "Complete Phase 3 before proceeding."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        bank_code = data["bank_code"]
        payload = {
            "account_number": data["account_number"],
            "bank_code": bank_code
        }
        try:
            paystack_resp = client.verfy_account(payload)
            bank_data = paystack_resp.get("data") or {}
            bank_success = bool(paystack_resp.get("status")) and bool(bank_data.get("account_name")) #old: bank_result["success"]
            resolved_account_name = bank_data.get("account_name") or data["account_name"]
            provider_ref = str(bank_data.get("bank_id") or "")
        except Exception as exc:
            bank_success = False
            bank_data = {"error": str(exc)}
            resolved_account_name = data["account_name"]
            provider_ref = ""

        DriverVerification.objects.update_or_create(
            driver=profile,
            verification_type=DriverVerification.TYPE_BANK_ACCOUNT,
            defaults={
                "status": DriverVerification.STATUS_SUCCESS if bank_success else DriverVerification.STATUS_FAILED,
                "provider_name": "paystack",
                "provider_ref": provider_ref,
                "request_payload": {"account_number": data["account_number"], "bank_code": bank_code},
                "response_payload": bank_data,
                "completed_at": timezone.now(),
            },
        )

        bank = Bank.objects.filter(code=bank_code).first()
        bank_name = bank.name if bank else ""

        bank_account, _ = DriverBankAccount.objects.get_or_create(driver=profile)
        bank_account.bank_name = bank_name
        bank_account.bank_code = bank_code
        bank_account.bank_account_number = data["account_number"]
        # Use Paystack-resolved name if available, else trust driver input
        bank_account.bank_account_name = resolved_account_name
        bank_account.is_verified = bank_success
        bank_account.verified_at = timezone.now()
        bank_account.save()

        needs_manual_review = not bank_success

        # ── Snapshot & mark complete ──
        answers["phase_4"] = {
            "bank_name": bank_account.bank_name,
            "account_number": bank_account.bank_account_number,
            "account_name": bank_account.bank_account_name,
            "bank_verification_status": "verified" if bank_success else "failed",
            "needs_manual_review": needs_manual_review,
        }
        answers["phase_4_complete"] = True
        submission.answers = answers
        submission.status = DriverOnboardingSubmission.STATUS_SUBMITTED
        submission.submitted_at = timezone.now()
        submission.updated_at = timezone.now()
        submission.save(update_fields=["answers", "status", "submitted_at", "updated_at"])

        out = {
            "phase": 4,
            "status": "saved",
            "onboarding_complete": True,
            **answers["phase_4"],
        }
        if bank_success:
            from payments.payouts.tasks import ensure_paystack_recipient_for_driver
            ensure_paystack_recipient_for_driver.delay(profile.id)
        return Response(OnboardingPhase4OutputSerializer(out).data)
