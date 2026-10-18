from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status
from accounts.models import(
    User, Business, Branch, 
    BusinessAdmin, BusinessPayoutAccount, BranchOperatingHours, BusinessCerd, BusinessOnboardStatus,
    BusinessVerification,  # new model - see model_changes.md
)
from verification import service as verification_service
from payments.services.base import ensure_valid_cred
from payments.integrations.paystack.errors import PaystackAPIError
from django.db import transaction, IntegrityError
from authflow.services import (
    verify_phonenumber, OTPInvalidError
)
from authflow.authentication import CustomBAdminAuth
from authflow.permissions import IsBusinessAdmin
from addresses.utils import checkset_location
from drf_spectacular.utils import extend_schema, inline_serializer # type: ignore
from rest_framework import serializers as s
from accounts.serializers import InS, OpS
from menu.views import BatchGenerateUploadURLView, RegisterMenusPhase3View  # noqa: F401
from business_api.views import BaseBuisAdminAPIView
from common.phone.utils import get_phone_number
from image.views import ImageMixin
from authflow.services.jwt import issue_jwt_for_user_with_plan
from accounts.services.profiles import (
    PROFILE_BUSINESS_ADMIN,
)

# edge case of going back
@extend_schema(
    responses=OpS.OnboardResponseSerializer,
)
class BusinessOnboardingStatusView(APIView):
    authentication_classes = [CustomBAdminAuth]
    permission_classes = [IsBusinessAdmin]
    def get(self, request):
        Bstatus:BusinessOnboardStatus = BusinessOnboardStatus.objects.filter(admin=request.user.business_admin).first()
        
        if not Bstatus:
            data = {
                "onboarding_step": 0,
                "is_onboarding_complete": False,
            }
        else:
            data = {
            "onboarding_step": Bstatus.onboarding_step,
            "is_onboarding_complete": Bstatus.is_onboarding_complete,
        }
        response_data = OpS.OnboardResponseSerializer(data)
        return Response(response_data.data, status=status.HTTP_200_OK)

# add a update method that reqiures jwt
@extend_schema(
    responses=OpS.RegisterBAdminResponseSerializer,
    auth=[]
)
class RegisterBAdmin(GenericAPIView):
    """
    PUT /business/admin/register/

    Combines what used to be two separate endpoints:
      - RegisterBAdmin (POST, AllowAny)   - first-time signup
      - ReRegisterBAdmin (POST, authenticated) - update your own details
    """
    serializer_class = InS.RegisterBAdminSerializer
    permission_classes = [AllowAny]

    def put(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        try:
            identifier = vd["phone_number"]
            # identifier = verify_phonenumber(vd["otp_code"], get_phone_number(vd["phone_number"]), vd["pin_id"])
        except OTPInvalidError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                user, is_new = User.objects.get_or_create(
                    phone_number=identifier,
                    defaults={"email": vd["email"]},
                )
                if not is_new:
                    user.email = vd["email"]
                    user.save(update_fields=["email"])

                business_admin, _ = BusinessAdmin.objects.get_or_create(user=user)
                business_admin.name = vd["full_name"]
                business_admin.save(update_fields=["name"])

                BusinessOnboardStatus.objects.get_or_create(
                    admin=business_admin, defaults={"onboarding_step": 0}
                )
        except IntegrityError as e:
            return Response(
                {"error": f"Registration failed due to a database constraint: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            return Response(
                {"detail": f"Registration failed: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        token = issue_jwt_for_user_with_plan(user, active_profile=PROFILE_BUSINESS_ADMIN)

        response_data = OpS.RegisterBAdminResponseSerializer({
            "message": "User registered successfully" if is_new else "User details updated successfully",
            "refresh": token["refresh"],
            "access": token["access"],
            "user": {"id": user.id, "name": business_admin.name},
        })
        return Response(response_data.data, status=status.HTTP_201_CREATED if is_new else status.HTTP_200_OK)

def _biz_ref_from(result: dict) -> str:
    """Best-effort pull of a provider reference out of a verification.service result."""
    data = result.get("data") if result else None
    if not isinstance(data, dict):
        return ""
    for key in ("reference", "tracking_id", "entity_id", "id"):
        if data.get(key):
            return str(data[key])
    return ""


@extend_schema(
    responses={201: inline_serializer("Phase2Response", fields={
        "details": s.CharField(),
        "business_id": s.CharField(),
    })}
)
class RestaurantPhase1RegisterView(BaseBuisAdminAPIView, ImageMixin):
    """
    Phase 1: Business + admin registration details.

    PUT, not POST — same pattern as the driver onboarding phases: call
    this again with corrected data to fix a mistake. It updates the
    existing Business in place rather than creating a duplicate. Locked
    only once onboarding is fully complete (same lock point Phase 2
    uses) - not on the first successful call, so this really is
    "correctable until final submit," not "correctable exactly once."
    """
    serializer_class = InS.RestaurantPhase1Serializer
    def put(self, request):
        business_admin = self.get_buisnessadmn(request)

        onboard_status = BusinessOnboardStatus.objects.filter(admin=business_admin).first()
        if onboard_status and onboard_status.is_onboarding_complete:
            return Response(
                {"detail": "Onboarding is already complete. Contact support to update your business details."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data
        user = request.user
        files: dict = request.FILES

        try:
            with transaction.atomic():
                business_image = files.get("business_image")
                business_logo = files.get("business_image")
                if business_image:
                    self.validate_image(business_image)
                if business_logo:
                    self.validate_image(business_logo)

                business_fields = dict(
                    business_name=vd["business_name"],
                    business_type=vd["business_type"],
                    country=vd["country"],
                    business_address=vd["business_address"],
                    email=vd["email"],
                    phone_number=vd["phone_number"],
                )
                if business_image:
                    business_fields["business_image"] = business_image
                if business_logo:
                    business_fields["business_logo"] = business_logo

                if business_admin.business_id:
                    # Correcting an in-progress registration - update the
                    # existing Business instead of creating a duplicate/
                    # orphan row and re-pointing business_admin at it.
                    business = business_admin.business
                    for field, value in business_fields.items():
                        setattr(business, field, value)
                    business.save()
                    is_new = False
                else:
                    business = Business.objects.create(**business_fields)
                    BusinessCerd.objects.create(business=business)
                    BusinessAdmin.objects.filter(id=business_admin.id).update(business=business)
                    is_new = True

                # NOTE: password is still required by the serializer on every
                # call, so correcting e.g. just the address also means
                # resupplying the password. Worth making it optional on
                # resubmission if that's awkward for your frontend - didn't
                # touch InS.RestaurantPhase1Serializer since it wasn't in
                # what you uploaded this round.
                user.set_password(vd["password"])
                user.save()

                BusinessOnboardStatus.objects.filter(admin=business_admin).update(onboarding_step=1)

            return Response(
                {
                    "detail": "Business registered. Proceed to onboarding." if is_new else "Business details updated.",
                    "business_id": business.id,
                },
                status=status.HTTP_201_CREATED if is_new else status.HTTP_200_OK,
            )
        except ValueError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

@extend_schema(
    responses={200: inline_serializer("Phase1Response", fields={
        "details": s.CharField(),
    })}
)
class RestaurantPhase2OnboardingView(GenericAPIView):
    """
    Phase 2: Full business details — documents, image, payment, operations, branches.
    Requires the admin to be authenticated.

    """
    authentication_classes = [CustomBAdminAuth]
    permission_classes = [IsBusinessAdmin]
    serializer_class = InS.RestaurantPhase2Serializer
    def put(self, request):
        user = request.user
        try:
            admin = user.business_admin
        except BusinessAdmin.DoesNotExist:
            return Response({"detail": "Not a restaurant admin."}, status=status.HTTP_403_FORBIDDEN)

        restaurant:Business = admin.business
        restaurant_cerds = admin.business.cerd

        onboard_status = BusinessOnboardStatus.objects.filter(admin=admin).first()
        # Reentrance guard: without this, an admin whose business is already
        # fully onboarded could keep POSTing here and silently rewrite their
        # RC number, TIN, and bank/BVN details with onboarding_complete
        # re-set to True every time, no re-review involved.
        if onboard_status and onboard_status.is_onboarding_complete:
            return Response(
                {"detail": "Onboarding is already complete. Contact support to update your business details."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        # ── Verification calls happen outside the DB transaction (no point
        #    holding locks/a long transaction open across external HTTP calls) ──
        tin = vd.get("tax_identification_number", "")
        rc_number = vd.get("rc_number", "")
        payment_data = vd.get("payment", {})
        bvn = payment_data.get("bvn") if payment_data else None

        tin_result = verification_service.verify_tin(tin) if tin else None
        rc_result = verification_service.verify_rc_number(rc_number) if rc_number else None
        bvn_result = verification_service.verify_business_bvn(bvn) if bvn else None

        # A check that was never run (field left blank) isn't a "failure" -
        # only an attempted-and-failed check should force manual review.
        needs_manual_review = any(
            result is not None and not result["success"]
            for result in (tin_result, rc_result, bvn_result)
        )

        with transaction.atomic():
            # Update restaurant details
            restaurant_cerds.registered_business_name = vd.get("registered_business_name", restaurant.business_name)
            restaurant_cerds.bn_number = vd.get("bn_number", "")
            restaurant_cerds.rc_number = rc_number
            restaurant_cerds.tax_identification_number = tin
            restaurant_cerds.business_type = vd.get("business_type", restaurant.business_type)
            restaurant_cerds.doc_type = vd.get("doctype", "cac")

            if "business_documents" in request.FILES:
                restaurant_cerds.business_doc = request.FILES["business_documents"]

            for verification_type, result, payload in (
                (BusinessVerification.TYPE_TIN, tin_result, {"tin": tin}),
                (BusinessVerification.TYPE_RC, rc_result, {"rc_number": rc_number}),
                (BusinessVerification.TYPE_BVN, bvn_result, {"bvn": (bvn or "")[-4:].zfill(11)}),  # masked
            ):
                if result is None:
                    continue
                BusinessVerification.objects.update_or_create(
                    business=restaurant,
                    verification_type=verification_type,
                    defaults={
                        "status": BusinessVerification.STATUS_SUCCESS if result["success"] else BusinessVerification.STATUS_FAILED,
                        "provider_name": result["provider"] or "",
                        "provider_ref": _biz_ref_from(result),
                        "request_payload": payload,
                        "response_payload": result["data"] if result["success"] else {"attempts": result["attempts"]},
                        "completed_at": timezone.now(),
                    },
                )

            restaurant.onboarding_complete = not needs_manual_review# remove
            restaurant_cerds.save()
            restaurant.save()
            BusinessOnboardStatus.objects.filter(admin=admin).update(
                onboarding_step=2,
                needs_manual_review=needs_manual_review,
                checked=False,
            )

            # Payment info
            if payment_data:
                BusinessPayoutAccount.objects.update_or_create(
                    business=restaurant,
                    defaults={
                        "bank_name": payment_data["bank"],
                        "bank_code": payment_data.get("bank_code", ""),
                        "bank_account_number": payment_data["account_number"],
                        "bank_account_name": payment_data["account_name"],
                        "bvn": payment_data["bvn"][-4:],
                        "bvn_verification_ref": _biz_ref_from(bvn_result) if bvn_result else "",
                    },
                )
            
            # Branches + operating hours
            branches_data = vd.get("branches", [])
            if len(branches_data) <= 3:
                self.sync_branches_simple(restaurant, branches_data)
            else:
                self.sync_branches_bulk(restaurant, branches_data)

        return Response(
            {
                "detail": "Onboarding submitted." if needs_manual_review else "Onboarding complete.",
                "needs_manual_review": needs_manual_review,
            },
            status=status.HTTP_200_OK,
        )
    
    def sync_branches_bulk(self, restaurant, branches_data):
        
        # -----------------------------------
        # FETCH EXISTING BRANCHES ONCE
        # -----------------------------------
        existing_branches = {
            (b.business_id, b.name): b
            for b in Branch.objects.filter(
                business=restaurant,
                name__in=[b["name"] for b in branches_data]
            )
        }

        branches_to_create = []
        branches_to_update = []

        for branch_data in branches_data:
            key = (restaurant.id, branch_data["name"])

            defaults = {
                "address": branch_data.get("address", "unknown"),
                "location": checkset_location(branch_data),
                "delivery_method": branch_data.get("delivery_method", "instant"),
                "pre_order_open_period": branch_data.get("pre_order_open_period"),
                "final_order_time": branch_data.get("final_order_time"),
            }

            branch = existing_branches.get(key)

            if branch:
                for field, value in defaults.items():
                    setattr(branch, field, value)

                branches_to_update.append(branch)

            else:
                branch = Branch(
                    business=restaurant,
                    name=branch_data["name"],
                    **defaults
                )

                branches_to_create.append(branch)
                existing_branches[key] = branch

        # -----------------------------------
        # BULK CREATE
        # -----------------------------------
        Branch.objects.bulk_create(branches_to_create)

        # -----------------------------------
        # BULK UPDATE
        # -----------------------------------
        Branch.objects.bulk_update(
            branches_to_update,
            fields=[
                "address",
                "location",
                "delivery_method",
                "pre_order_open_period",
                "final_order_time",
            ]
        )

        # -----------------------------------
        # REFRESH CREATED IDS
        # -----------------------------------
        all_branches = {
            b.name: b
            for b in Branch.objects.filter(
                business=restaurant,
                name__in=[b["name"] for b in branches_data]
            )
        }

        # -----------------------------------
        # OPERATING HOURS
        # -----------------------------------
        hours_to_upsert = []

        for branch_data in branches_data:
            branch = all_branches[branch_data["name"]]

            for h in branch_data.get("operating_hours", []):
                hours_to_upsert.append(
                    BranchOperatingHours(
                        branch=branch,
                        day=h["day"],
                        open_time=h["open_time"],
                        close_time=h["close_time"],
                        is_closed=h.get("is_closed", False),
                    )
                )

        BranchOperatingHours.objects.bulk_create(
            hours_to_upsert,
            update_conflicts=True,
            unique_fields=["branch", "day"],
            update_fields=["open_time", "close_time", "is_closed"],
        )

    def sync_branches_simple(self, restaurant, branches_data):
        for branch_data in branches_data:
            branch, _ = Branch.objects.update_or_create(
                business=restaurant,
                name=branch_data["name"],
                defaults={
                    "address": branch_data.get("address", "unknown"),
                    "location": checkset_location(branch_data),
                    "delivery_method": branch_data.get("delivery_method", "instant"),
                    "pre_order_open_period": branch_data.get("pre_order_open_period"),
                    "final_order_time": branch_data.get("final_order_time"),
                },
            )
            hours_data = branch_data.get("operating_hours", [])
            BranchOperatingHours.objects.bulk_create(
                [
                    BranchOperatingHours(
                        branch=branch,
                        day=h["day"],
                        open_time=h["open_time"],
                        close_time=h["close_time"],
                        is_closed=h.get("is_closed", False),
                    )
                    for h in hours_data
                ], 
                update_conflicts=True,
                unique_fields=["branch", "day"],   # 🔥 what makes a row unique
                update_fields=["open_time", "close_time", "is_closed"],  # 🔥 what to update
            )
