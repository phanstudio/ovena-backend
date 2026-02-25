from django.urls import path, include
from .views import (
    VerifyOTPView, UserProfileView, DeleteAccountView, UpdateBranch, Delete2AccountView,
    OAuthExchangeView, RegisterRManager, RegisterCustomer, UpdateCustomer,
    jwt_views, SendEmailOTPView, VerifyEmailOTPView, RegisterBAdmin, SendPhoneOTPView,
    RestaurantPhase2OnboardingView, RestaurantPhase1RegisterView, 
    PasswordResetView, AdminLoginView, DriverLoginView
)
from menu.views import RegisterMenusPhase3View, BatchGenerateUploadURLView

token_urls = [
    path("rotate-token/", jwt_views.RotateTokenView.as_view(), name="rotate-token"),
    path("refresh/", jwt_views.RefreshTokenView.as_view(), name="refresh"),
    path("logout/", jwt_views.LogoutView.as_view(), name="logout"),
    path("login/", jwt_views.LogInView.as_view(), name="login"),
]

onboarding_urls = [
    # make sure you send otp before
    path("admin/", RegisterBAdmin.as_view(), name="register-businessadmin"),
    path("phase1/", RestaurantPhase1RegisterView.as_view(), name="register-phase1"),
    path("phase2/", RestaurantPhase2OnboardingView.as_view(), name="register-phase2"),
    path("phase3/", RegisterMenusPhase3View.as_view(), name="register-menus-ob"),
    path("batch-gen-url/", BatchGenerateUploadURLView.as_view(), name="batch-generate-url"),
]

account_urls = [
    path("admin-login/", AdminLoginView.as_view(), name="admin-login"),
    path("driver-login/", DriverLoginView.as_view(), name="admin-login"),
    path("password-reset/", PasswordResetView.as_view(), name="password-reset"),
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
    path("", include(account_urls)),
]
