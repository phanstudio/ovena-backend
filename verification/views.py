import requests
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .serializers import (
    NINVerificationSerializer,
    BVNVerificationSerializer,
    BVNValidationSerializer,
    AccountNumberSerializer,
    FaceMatchSerializer,
    PlateNumberSerializer,
    TINVerificationSerializer,
    RCNumberSerializer,
    BusinessBVNSerializer,
)
from . import services


def _dojah_error(exc: requests.HTTPError) -> Response:
    """Normalise Dojah HTTP errors into a consistent API response."""
    try:
        detail = exc.response.json()
    except Exception:
        detail = str(exc)
    return Response(
        {"success": False, "error": detail},
        status=exc.response.status_code if exc.response is not None else 502,
    )


# ──────────────────────────────────────────────
# DRIVER VIEWS
# ──────────────────────────────────────────────

class NINVerificationView(APIView):
    """
    POST /api/verify/driver/nin/
    Verify a driver's National Identification Number.
    """

    def post(self, request):
        serializer = NINVerificationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = services.verify_nin(serializer.validated_data["nin"])
            return Response({"success": True, "data": result})
        except requests.HTTPError as exc:
            return _dojah_error(exc)


class BVNVerificationView(APIView):
    """
    POST /api/verify/driver/bvn/
    Look up a driver's BVN and return full identity details.
    """

    def post(self, request):
        serializer = BVNVerificationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = services.verify_bvn(serializer.validated_data["bvn"])
            return Response({"success": True, "data": result})
        except requests.HTTPError as exc:
            return _dojah_error(exc)


class BVNValidationView(APIView):
    """
    POST /api/verify/driver/bvn/validate/
    Validate BVN by matching it against supplied name / date-of-birth.
    Returns per-field confidence scores.
    """

    def post(self, request):
        serializer = BVNValidationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        try:
            result = services.validate_bvn(
                bvn=data["bvn"],
                first_name=data.get("first_name"),
                last_name=data.get("last_name"),
                dob=str(data["dob"]) if data.get("dob") else None,
            )
            return Response({"success": True, "data": result})
        except requests.HTTPError as exc:
            return _dojah_error(exc)


class AccountNumberVerificationView(APIView):
    """
    POST /api/verify/driver/account/
    Verify a bank account number (NUBAN) and retrieve account name.
    """

    def post(self, request):
        serializer = AccountNumberSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        try:
            result = services.verify_account_number(
                account_number=data["account_number"],
                bank_code=data["bank_code"],
            )
            return Response({"success": True, "data": result})
        except requests.HTTPError as exc:
            return _dojah_error(exc)


class FaceMatchView(APIView):
    """
    POST /api/verify/driver/face-match/
    Match a selfie against BVN or NIN government data.
    Body: { image (base64), first_name, last_name, bvn? | nin? }
    """

    def post(self, request):
        serializer = FaceMatchSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        try:
            result = services.match_face_to_name(
                image=data["image"],
                first_name=data["first_name"],
                last_name=data["last_name"],
                bvn=data.get("bvn"),
                nin=data.get("nin"),
            )
            return Response({"success": True, "data": result})
        except requests.HTTPError as exc:
            return _dojah_error(exc)


class PlateNumberVerificationView(APIView):
    """
    POST /api/verify/driver/plate/
    Verify a Nigerian vehicle plate number.
    """

    def post(self, request):
        serializer = PlateNumberSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = services.verify_plate_number(
                serializer.validated_data["plate_number"]
            )
            return Response({"success": True, "data": result})
        except requests.HTTPError as exc:
            return _dojah_error(exc)


# ──────────────────────────────────────────────
# BUSINESS VIEWS
# ──────────────────────────────────────────────

class TINVerificationView(APIView):
    """
    POST /api/verify/business/tin/
    Verify a company Tax Identification Number via FIRS.
    """

    def post(self, request):
        serializer = TINVerificationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = services.verify_tin(serializer.validated_data["tin"])
            return Response({"success": True, "data": result})
        except requests.HTTPError as exc:
            return _dojah_error(exc)


class RCNumberVerificationView(APIView):
    """
    POST /api/verify/business/rc/
    Verify a CAC RC number and retrieve company details and directors.
    """

    def post(self, request):
        serializer = RCNumberSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = services.verify_rc_number(serializer.validated_data["rc_number"])
            return Response({"success": True, "data": result})
        except requests.HTTPError as exc:
            return _dojah_error(exc)


class BusinessBVNVerificationView(APIView):
    """
    POST /api/verify/business/bvn/
    Verify the BVN of a business owner or director.
    """

    def post(self, request):
        serializer = BusinessBVNSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = services.verify_business_bvn(serializer.validated_data["bvn"])
            return Response({"success": True, "data": result})
        except requests.HTTPError as exc:
            return _dojah_error(exc)
