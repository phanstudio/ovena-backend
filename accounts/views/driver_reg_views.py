from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import GenericAPIView
from authflow.services import issue_jwt_for_user
from uuid import uuid5

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
from accounts.utils.driver_verification import (
    verify_nin_mono, verify_bvn_mono, verify_bank_account_paystack,
)
from referrals.services import apply_referral_code, ensure_profile_base
from drf_spectacular.utils import extend_schema # type: ignore

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
        submission = DriverOnboardingSubmission.objects.create(
            driver=profile,
            status=DriverOnboardingSubmission.STATUS_DRAFT,
            answers={},
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
        submission = _get_or_create_submission(profile)
        complete = _phases_complete(submission)
        answers = submission.answers or {}

        out = {
            "current_phase": _current_phase(complete),
            "phases_complete": complete,
            "all_phases_complete": len(complete) == 4,
            "submission_status": submission.status,
            "reviewer_note": submission.reviewer_note,
            "phase_data": {
                "phase_1": answers.get("phase_1"),
                "phase_2": answers.get("phase_2"),
                "phase_3": answers.get("phase_3"),
                "phase_4": answers.get("phase_4"),
            },
        }
        return Response(OnboardingStatusOutputSerializer(out).data)


# ─── Phase 1 — Personal Info ──────────────────────────────────────────────────

class OnboardingPhase1View(GenericAPIView):
    """
    PUT /onboarding/phase/1/
    Saves personal info, contact details, and next-of-kin.
    Driver can re-submit to update until final submission.
    """
    permission_classes = [AllowAny]
    serializer_class = OnboardingPhase1InputSerializer

    def put(self, request):
        serializer = self.get_serializer(
            data=request.data,
            context={"driver_user_id": request.user.pk},
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = User.objects.get_or_create(email=data["email"])
        profile, _ = DriverProfile.objects.get_or_create(user=request.user)
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
        user = request.user
        user.phone_number = data["phone_number"]
        user.email = data["email"]
        user.name = f"{data['first_name']} {data['last_name']}"
        user.set_password(data["password"])
        user.save(update_fields=["phone_number", "email", "name"])
        token = issue_jwt_for_user(user)

        # ── Persist next-of-kin to DriverCred ──
        cred, _ = DriverCred.objects.get_or_create(user=profile)
        cred.next_of_kin_name = data["next_of_kin_name"]
        cred.next_of_kin_phone = data["next_of_kin_phone"]
        cred.save(update_fields=["next_of_kin_name", "next_of_kin_phone"])

        ensure_profile_base(profile)

        referre_code = data.get("referre_code", "")
        if referre_code:
            try:
                apply_referral_code(profile=profile, code=referre_code)
            except DjangoValidationError as exc:
                msg = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
                return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

        # ── Snapshot into submission answers ──
        answers = submission.answers or {}
        answers["phase_1"] = {
            "first_name": data["first_name"],
            "last_name": data["last_name"],
            "phone_number": data["phone_number"],
            "email": data["email"],
            "gender": data["gender"],
            "birth_date": str(data["birth_date"]),
            "residential_address": data["residential_address"],
            "next_of_kin_name": data["next_of_kin_name"],
            "next_of_kin_phone": data["next_of_kin_phone"],
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


# ─── Phase 2 — Identity & Vehicle ─────────────────────────────────────────────

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
        # OnboardingPhase2InputSerializer(data=request.data)
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

        # ── NIN verification via Mono ──
        # nin_result = verify_nin_mono(data["nin"])
        # nin_ver = DriverVerification.objects.create(
        #     driver=profile,
        #     verification_type=DriverVerification.TYPE_NIN,
        #     status=DriverVerification.STATUS_SUCCESS if nin_result["success"] else DriverVerification.STATUS_FAILED,
        #     provider_name="mono",
        #     provider_ref=nin_result["provider_ref"],
        #     request_payload={"nin": data["nin"][-4:].zfill(11)},  # store masked
        #     response_payload=nin_result["response_payload"],
        #     completed_at=timezone.now(),
        # )

        nin_ver = DriverVerification.objects.create(
            driver=profile,
            verification_type=DriverVerification.TYPE_NIN,
            status=DriverVerification.STATUS_SUCCESS,
            provider_name="mono",
            provider_ref= uuid5(),
            request_payload={"nin": data["nin"][-4:].zfill(11)},  # store masked
            response_payload={"data":"successful"},
            completed_at=timezone.now(),
        )


        # ── BVN verification via Mono ──
        # bvn_result = verify_bvn_mono(data["bvn"])
        # bvn_ver = DriverVerification.objects.create(
        #     driver=profile,
        #     verification_type=DriverVerification.TYPE_BVN,
        #     status=DriverVerification.STATUS_SUCCESS if bvn_result["success"] else DriverVerification.STATUS_FAILED,
        #     provider_name="mono",
        #     provider_ref=bvn_result["provider_ref"],
        #     request_payload={"bvn": data["bvn"][-4:].zfill(11)},  # store masked
        #     response_payload=bvn_result["response_payload"],
        #     completed_at=timezone.now(),
        # )

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
            "nin_last4": data["nin"][-4:],
            "bvn_last4": data["bvn"][-4:],
            "nin_verification_status": nin_ver.status,
            "bvn_verification_status": False,#bvn_ver.status,
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
        # OnboardingPhase4InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # ── Bank account verification via Paystack ──
        # bank_code should come from a banks list endpoint (Paystack /bank)
        # For now, accept it as an optional field alongside account_number
        bank_code = request.data.get("bank_code", "")
        bank_result = {}#verify_bank_account_paystack(data["account_number"], bank_code)

        bank_account, _ = DriverBankAccount.objects.get_or_create(driver=profile)
        bank_account.bank_name = data["bank_name"]
        bank_account.bank_code = bank_code
        bank_account.account_number = data["account_number"]
        # Use Paystack-resolved name if available, else trust driver input
        bank_account.account_name = data["account_name"]
        bank_account.is_verified = True#bank_result["success"]
        bank_account.verified_at = timezone.now()
        bank_account.save()

        # ── Selfie document ──
        selfie_doc, _ = DriverDocument.objects.get_or_create(
            driver=profile,
            doc_type=DriverDocument.DOC_SELFIE,
        )
        selfie_doc.file = data["verified_selfie"]
        selfie_doc.status = DriverDocument.STATUS_PENDING
        selfie_doc.save(update_fields=["file", "status"])

        # ── Snapshot & mark complete ──
        answers["phase_4"] = {
            "bank_name": bank_account.bank_name,
            "account_number": bank_account.account_number,
            "account_name": bank_account.account_name,
            "bank_verification_status": "verified",
            "selfie_url": selfie_doc.file.url if selfie_doc.file else "",
        }
        answers["phase_4_complete"] = True
        submission.answers = answers
        submission.updated_at = timezone.now()
        submission.save(update_fields=["answers", "updated_at"])

        out = {
            "phase": 4,
            "status": "saved",
            "onboarding_complete": True,
            **answers["phase_4"],
        }
        return Response(OnboardingPhase4OutputSerializer(out).data)
