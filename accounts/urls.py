from django.urls import path, include
from .views import (
    VerifyOTPView, UserProfileView, DeleteAccountView, UpdateBranch, Delete2AccountView,
    OAuthExchangeView, RegisterRManager, RegisterCustomer, UpdateCustomer,
    jwt_views, SendEmailOTPView, VerifyEmailOTPView, RegisterBAdmin, SendPhoneOTPView,
    PasswordResetView, AdminLoginView, DriverLoginView
)
from .views import driver_reg_views

token_urls = [
    path("rotate-token/", jwt_views.RotateTokenView.as_view(), name="rotate-token"),
    path("refresh/", jwt_views.RefreshTokenView.as_view(), name="refresh"),
    path("logout/", jwt_views.LogoutView.as_view(), name="logout"), # for 
    path("login/", jwt_views.LogInView.as_view(), name="login"),
]

onboarding_urls = [
    # make sure you send otp before
    path("admin/", RegisterBAdmin.as_view(), name="register-businessadmin"),
    path("", include("business_api.legacy_onboarding_urls")),
]

account_urls = [
    path("admin-login/", AdminLoginView.as_view(), name="admin-login"),
    path("driver-login/", DriverLoginView.as_view(), name="admin-login"),
    path("password-reset/", PasswordResetView.as_view(), name="password-reset"),
]


driver_onboarding_urls = [
    # Progress overview — call this on app open to know where driver left off
    path("status/", driver_reg_views.OnboardingStatusView.as_view(), name="onboarding-status"),

    # Phase endpoints — all PUT, idempotent, re-editable until submitted
    path("phase/1/", driver_reg_views.OnboardingPhase1View.as_view(), name="onboarding-phase-1"),
    path("phase/2/", driver_reg_views.OnboardingPhase2View.as_view(), name="onboarding-phase-2"),
    path("phase/3/", driver_reg_views.OnboardingPhase3View.as_view(), name="onboarding-phase-3"),
    path("phase/4/", driver_reg_views.OnboardingPhase4View.as_view(), name="onboarding-phase-4"),
]


urlpatterns = [
    path("send-otp/", SendPhoneOTPView.as_view(), name="send-otp"),
    path("verify-otp/", VerifyOTPView.as_view(), name="verify-otp"),
    # path("link-approval/", LinkApprove.as_view(), name="link-approval"),
    # path("link-request/", LinkRequestCreate.as_view(), name="link-request-create"),
    path("register-manager/", RegisterRManager.as_view(), name="register-rmanager"),
    path("register-user/", RegisterCustomer.as_view(), name="register-user"),
    path("oauth/exchange/", OAuthExchangeView.as_view(), name="oauth-exchange"),
    path("profile/", UserProfileView.as_view(), name="user-profile"),
    path("customer/update/", UpdateCustomer.as_view(), name="user-update"),
    path("profile/delete/", DeleteAccountView.as_view(), name="user-delete"),
    path("profile/delete2/", Delete2AccountView.as_view(), name="user-delete"),

    path("send-email-otp/", SendEmailOTPView.as_view(), name="send-email-otp"),
    path("verify-email-otp/", VerifyEmailOTPView.as_view(), name="verify-email-otp"),

    path("branches/<int:branch_id>/update/", UpdateBranch.as_view()),
    path("", include(token_urls)),
    path("onboard/", include(onboarding_urls)),
    path("onboard/driver/", include(driver_onboarding_urls)),
    path("", include(account_urls)),
]
