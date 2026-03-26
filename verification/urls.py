from django.urls import path
from . import views

# Include this in your project's urls.py:
# path("api/verify/", include("dojah_verification.urls")),

urlpatterns = [
    # ── Driver Verifications ──────────────────────────────────────
    path("driver/nin/",          views.NINVerificationView.as_view(),         name="verify-driver-nin"),
    path("driver/bvn/",          views.BVNVerificationView.as_view(),         name="verify-driver-bvn"),
    path("driver/bvn/validate/", views.BVNValidationView.as_view(),           name="verify-driver-bvn-validate"),
    path("driver/account/",      views.AccountNumberVerificationView.as_view(), name="verify-driver-account"),
    path("driver/face-match/",   views.FaceMatchView.as_view(),               name="verify-driver-face-match"),
    path("driver/plate/",        views.PlateNumberVerificationView.as_view(), name="verify-driver-plate"),

    # ── Business Verifications ────────────────────────────────────
    path("business/tin/",        views.TINVerificationView.as_view(),         name="verify-business-tin"),
    path("business/rc/",         views.RCNumberVerificationView.as_view(),    name="verify-business-rc"),
    path("business/bvn/",        views.BusinessBVNVerificationView.as_view(), name="verify-business-bvn"),
]
