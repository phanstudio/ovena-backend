from django.urls import path, include
from .views import (
    VerifyOTPView, UserProfileView, DeleteAccountView, Delete2AccountView,
    OAuthExchangeView, RegisterCustomer, UpdateCustomer, LinkApproveView,
    jwt_views, SendEmailOTPView, VerifyEmailOTPView, SendPhoneOTPView,
    PasswordResetView, AdminLoginView, DriverLoginView, LinkRequestCreateView, 
    StaffLoginView, PassWordResetSendView, ChangePasswordView
)
from .views import driver_reg_views
from .views import business_reg_views

token_urls = [
    path("rotate-token/", jwt_views.RotateTokenView.as_view(), name="rotate-token"),
    path("refresh/", jwt_views.RefreshTokenView.as_view(), name="refresh"),
    path("logout/", jwt_views.LogoutView.as_view(), name="logout"), # for 
    path("login/", jwt_views.LogInView.as_view(), name="login"),
]

onboarding_urls = [
    # make sure you send otp before
    path("admin/", business_reg_views.RegisterBAdmin.as_view(), name="register-businessadmin"),
    path("re/admin/", business_reg_views.ReRegisterBAdmin.as_view(), name="reregister-businessadmin"),
    path("phase1/", business_reg_views.RestaurantPhase1RegisterView.as_view(), name="business-register-phase1"),
    path("phase2/", business_reg_views.RestaurantPhase2OnboardingView.as_view(), name="business-register-phase2"),
    path("phase3/", business_reg_views.RegisterMenusPhase3View.as_view(), name="business-register-menus-ob"),
    path("batch-gen-url/", business_reg_views.BatchGenerateUploadURLView.as_view(), name="business-batch-generate-url"),
    path("status/", business_reg_views.BuisnnessOnboardingStatusView.as_view(), name="business-onboard-status"),
]

account_urls = [
    path("admin-login/", AdminLoginView.as_view(), name="admin-login"),
    path("driver-login/", DriverLoginView.as_view(), name="driver-login"),
    path("password-reset/", PasswordResetView.as_view(), name="password-reset"),
    path("password-reset/send/", PassWordResetSendView.as_view(), name="password-reset-send"),
    path("staff-login/", StaffLoginView.as_view(), name="staff-login"),
    path("change-password/", ChangePasswordView.as_view(), name="change-password")
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

linked_user_urls = [
    path("approval/", LinkApproveView.as_view(), name="linked-user-approval"),
    path("request/", LinkRequestCreateView.as_view(), name="linked-user-request-create"),
]

urlpatterns = [
    path("send-otp/", SendPhoneOTPView.as_view(), name="send-otp"),
    path("verify-otp/", VerifyOTPView.as_view(), name="verify-otp"),
    
    path("register-user/", RegisterCustomer.as_view(), name="register-user"),
    path("oauth/exchange/", OAuthExchangeView.as_view(), name="oauth-exchange"),
    path("profile/", UserProfileView.as_view(), name="user-profile"),
    path("customer/update/", UpdateCustomer.as_view(), name="user-update"),
    path("profile/delete/", DeleteAccountView.as_view(), name="user-delete"),
    path("profile/delete2/", Delete2AccountView.as_view(), name="user-delete"),

    path("send-email-otp/", SendEmailOTPView.as_view(), name="send-email-otp"),
    path("verify-email-otp/", VerifyEmailOTPView.as_view(), name="verify-email-otp"),

    path("", include(token_urls)),
    path("onboard/", include(onboarding_urls)),
    path("onboard/driver/", include(driver_onboarding_urls)),
    path("", include(account_urls)),
    path("linked/", include(linked_user_urls)),
]
