import pytest
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import (
    DriverAvailability,
    DriverBankAccount,
    DriverCred,
    DriverDocument,
    DriverOnboardingSubmission,
    DriverProfile,
    DriverVerification,
)
from authflow.services import issue_jwt_for_user


pytestmark = pytest.mark.django_db


GIF_1PX = (
    b"GIF87a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!"
    b"\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00"
    b"\x00\x02\x02L\x01\x00;"
)


def make_image(name="test.gif"):
    return SimpleUploadedFile(name, GIF_1PX, content_type="image/gif")


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def driver_user():
    user_model = get_user_model()
    return user_model.objects.create(
        name="Test Driver",
        phone_number="+2348010000001",
        email="driver@example.com",
        role="driver",
    )


@pytest.fixture
def driver_profile(driver_user):
    return DriverProfile.objects.create(user=driver_user)


@pytest.fixture
def auth_client(api_client, driver_user):
    token = issue_jwt_for_user(driver_user)["access"]
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return api_client


@pytest.fixture
def phase1_payload():
    return {
        "first_name": "John",
        "last_name": "Doe",
        "phone_number": "+2348011112233",
        "email": "john.doe.driver@example.com",
        "gender": "male",
        "birth_date": "1998-01-10",
        "residential_address": "12 Driver Street, Ikeja",
        "next_of_kin_name": "Jane Doe",
        "next_of_kin_phone": "+2348014445566",
        "next_of_kin_address": "33 Kin Avenue, Surulere",
    }


def phase2_payload():
    return {
        "drivers_license": make_image("license.gif"),
        "nin": "12345678901",
        "bvn": "10987654321",
        "vehicle_type": "bike",
        "vehicle_make": "Honda",
        "plate_number": "LAG-123-AB",
        "guarantor1_name": "Guarantor One",
        "guarantor1_phone": "+2348010001000",
        "guarantor2_name": "Guarantor Two",
        "guarantor2_phone": "+2348010002000",
    }


def phase3_form_payload():
    return {
        "availability[0][weekday]": "1",
        "availability[0][time_mask]": "3",
        "availability[1][weekday]": "3",
        "availability[1][time_mask]": "4",
        "compliance_answers[have_you_worked_as_delivery_rider]": "yes",
        "compliance_answers[how_long_worked_as_rider]": "2 years",
        "compliance_answers[familiarity_with_local_routes]": "high",
        "compliance_answers[have_used_gps_for_deliveries]": "yes",
        "compliance_answers[can_handle_cash_on_delivery]": "yes",
        "compliance_answers[willing_to_follow_traffic_rules]": "yes",
        "compliance_answers[willing_to_wear_helmet_and_gear]": "yes",
        "compliance_answers[punctuality_self_rating]": "9",
        "compliance_answers[has_health_condition]": "no",
        "compliance_answers[why_work_with_us]": "Flexible work",
        "compliance_answers[how_soon_can_you_start]": "Immediately",
        "delivery_bag": make_image("bag.gif"),
    }


# def phase3_form_payload():
#     return {
#         "availability":[
#             {"weekday": "1",
#             "time_mask": "3",},
#             {"weekday": "3",
#             "time_mask": "4",}
#         ],
#         "compliance_answers": {
#             "have_you_worked_as_delivery_rider": "yes",
#             "how_long_worked_as_rider": "2 years",
#             "familiarity_with_local_routes": "high",
#             "have_used_gps_for_deliveries": "yes",
#             "can_handle_cash_on_delivery": "yes",
#             "willing_to_follow_traffic_rules": "yes",
#             "willing_to_wear_helmet_and_gear": "yes",
#             "punctuality_self_rating": "9",
#             "has_health_condition": "no",
#             "why_work_with_us": "Flexible work",
#             "how_soon_can_you_start": "Immediately",
#         },
#         "delivery_bag": make_image("bag.gif"),
#     }


def phase4_payload():
    return {
        "bank_name": "Demo Bank",
        "account_number": "0123456789",
        "account_name": "John Doe",
        "bank_code": "058",
        "verified_selfie": make_image("selfie.gif"),
    }


def test_status_requires_driver_profile(auth_client):
    url = reverse("onboarding-status")
    response = auth_client.get(url)

    assert response.status_code == 404


def test_status_creates_draft_submission(auth_client, driver_profile):
    url = reverse("onboarding-status")
    response = auth_client.get(url)

    assert response.status_code == 200
    assert response.data["current_phase"] == 1
    assert response.data["phases_complete"] == []
    assert response.data["all_phases_complete"] is False
    assert response.data["submission_status"] == DriverOnboardingSubmission.STATUS_DRAFT

    assert DriverOnboardingSubmission.objects.filter(driver=driver_profile).count() == 1


def test_phase1_updates_user_profile_and_creds(auth_client, driver_profile, phase1_payload):
    response = auth_client.put(reverse("onboarding-phase-1"), phase1_payload, format="json")
    assert response.status_code == 200
    assert response.data["phase"] == 1
    assert response.data["status"] == "saved"

    driver_profile.refresh_from_db()
    user = driver_profile.user
    user.refresh_from_db()
    submission = DriverOnboardingSubmission.objects.get(driver=driver_profile)
    cred = DriverCred.objects.get(user=driver_profile)

    assert driver_profile.first_name == "John"
    assert driver_profile.last_name == "Doe"
    assert user.phone_number == "+2348011112233"
    assert user.email == "john.doe.driver@example.com"
    assert user.name == "John Doe"
    assert cred.next_of_kin_name == "Jane Doe"
    assert submission.answers["phase_1_complete"] is True


def test_phase1_rejects_when_submission_is_submitted(auth_client, driver_profile, phase1_payload):
    DriverOnboardingSubmission.objects.create(
        driver=driver_profile,
        status=DriverOnboardingSubmission.STATUS_SUBMITTED,
        answers={},
    )

    response = auth_client.put(reverse("onboarding-phase-1"), phase1_payload, format="json")
    assert response.status_code == 400
    assert "already submitted" in response.data["detail"].lower()


def test_phase2_requires_phase1_complete(auth_client, driver_profile):
    response = auth_client.put(reverse("onboarding-phase-2"), {}, format="multipart")
    assert response.status_code == 400
    assert response.data["detail"] == "Complete Phase 1 before proceeding."


@patch("accounts.views.driver_reg_views.verify_nin_mono")
@patch("accounts.views.driver_reg_views.verify_bvn_mono")
def test_phase2_success_creates_verifications_and_document(
    mock_verify_bvn,
    mock_verify_nin,
    auth_client,
    driver_profile,
):
    DriverOnboardingSubmission.objects.create(
        driver=driver_profile,
        status=DriverOnboardingSubmission.STATUS_DRAFT,
        answers={"phase_1_complete": True},
    )
    mock_verify_nin.return_value = {
        "success": True,
        "provider_ref": "mono-nin-ref",
        "response_payload": {"status": "ok"},
        "error": None,
    }
    mock_verify_bvn.return_value = {
        "success": True,
        "provider_ref": "mono-bvn-ref",
        "response_payload": {"status": "ok"},
        "error": None,
    }

    response = auth_client.put(reverse("onboarding-phase-2"), phase2_payload(), format="multipart")

    assert response.status_code == 200
    assert response.data["phase"] == 2
    assert response.data["status"] == "saved"
    assert response.data["nin_verification_status"] == DriverVerification.STATUS_SUCCESS
    assert response.data["bvn_verification_status"] == DriverVerification.STATUS_SUCCESS

    submission = DriverOnboardingSubmission.objects.get(driver=driver_profile)
    cred = DriverCred.objects.get(user=driver_profile)
    verifications = DriverVerification.objects.filter(driver=driver_profile)
    documents = DriverDocument.objects.filter(driver=driver_profile)

    assert submission.answers["phase_2_complete"] is True
    assert cred.nin_last4 == "8901"
    assert cred.bvn_last4 == "4321"
    assert verifications.count() == 2
    assert documents.count() == 1


def test_phase3_requires_phase2_complete(auth_client, driver_profile):
    DriverOnboardingSubmission.objects.create(
        driver=driver_profile,
        status=DriverOnboardingSubmission.STATUS_DRAFT,
        answers={"phase_1_complete": True},
    )

    response = auth_client.put(reverse("onboarding-phase-3"), {}, format="multipart")
    assert response.status_code == 400
    assert response.data["detail"] == "Complete Phase 2 before proceeding."


def test_phase3_success_saves_availability_and_answers(auth_client, driver_profile):
    DriverOnboardingSubmission.objects.create(
        driver=driver_profile,
        status=DriverOnboardingSubmission.STATUS_DRAFT,
        answers={"phase_1_complete": True, "phase_2_complete": True},
    )

    response = auth_client.put(reverse("onboarding-phase-3"), phase3_form_payload(), format="multipart")

    print(response.json())
    assert response.status_code == 200
    assert response.data["phase"] == 3
    assert response.data["status"] == "saved"

    submission = DriverOnboardingSubmission.objects.get(driver=driver_profile)
    assert submission.answers["phase_3_complete"] is True
    assert DriverAvailability.objects.filter(driver=driver_profile).count() == 2
    assert DriverDocument.objects.filter(driver=driver_profile, doc_type=DriverDocument.DOC_DELIVERY_BAG).exists()


def test_phase4_requires_phase3_complete(auth_client, driver_profile):
    DriverOnboardingSubmission.objects.create(
        driver=driver_profile,
        status=DriverOnboardingSubmission.STATUS_DRAFT,
        answers={"phase_1_complete": True, "phase_2_complete": True},
    )

    response = auth_client.put(reverse("onboarding-phase-4"), {}, format="multipart")
    assert response.status_code == 400
    assert response.data["detail"] == "Complete Phase 3 before proceeding."


@patch("accounts.views.driver_reg_views.verify_bank_account_paystack")
def test_phase4_success_saves_bank_and_selfie(mock_verify_bank, auth_client, driver_profile):
    DriverOnboardingSubmission.objects.create(
        driver=driver_profile,
        status=DriverOnboardingSubmission.STATUS_DRAFT,
        answers={"phase_1_complete": True, "phase_2_complete": True, "phase_3_complete": True},
    )
    mock_verify_bank.return_value = {
        "success": True,
        "provider_ref": "paystack-ref",
        "account_name": "Verified John Doe",
        "response_payload": {"status": True},
        "error": None,
    }

    response = auth_client.put(reverse("onboarding-phase-4"), phase4_payload(), format="multipart")

    assert response.status_code == 200
    assert response.data["phase"] == 4
    assert response.data["status"] == "saved"
    assert response.data["onboarding_complete"] is True
    assert response.data["bank_verification_status"] == "verified"

    submission = DriverOnboardingSubmission.objects.get(driver=driver_profile)
    bank = DriverBankAccount.objects.get(driver=driver_profile)

    assert submission.answers["phase_4_complete"] is True
    assert bank.account_name == "Verified John Doe"
    assert bank.is_verified is True
    assert DriverDocument.objects.filter(driver=driver_profile, doc_type=DriverDocument.DOC_SELFIE).exists()


def test_status_reports_completed_progress(auth_client, driver_profile):
    DriverOnboardingSubmission.objects.create(
        driver=driver_profile,
        status=DriverOnboardingSubmission.STATUS_DRAFT,
        answers={
            "phase_1_complete": True,
            "phase_2_complete": True,
            "phase_3_complete": True,
            "phase_4_complete": True,
            "phase_1": {"first_name": "Jane"},
        },
    )

    response = auth_client.get(reverse("onboarding-status"))
    assert response.status_code == 200
    assert response.data["current_phase"] == 4
    assert response.data["phases_complete"] == [1, 2, 3, 4]
    assert response.data["all_phases_complete"] is True
    assert response.data["phase_data"]["phase_1"]["first_name"] == "Jane"
