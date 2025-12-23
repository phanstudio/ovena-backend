from django.urls import path, include
from .views import (
    SendOTPView, VerifyOTPView, UserProfileView, DeleteAccountView,
    OAuthExchangeView, LinkRequestCreate, LinkApprove, RegisterRManager, RegisterCustomer, 
    jwt_views
)

token_urls = [
    path("rotate-token/", jwt_views.RotateTokenView.as_view(), name="rotate-token"),
    path("refresh/", jwt_views.RefreshTokenView.as_view(), name="refresh"),
    path("logout/", jwt_views.LogoutView.as_view(), name="logout"),
    path("login/", jwt_views.LogInView.as_view(), name="login"),
]

urlpatterns = [
    path("send-otp/", SendOTPView.as_view(), name="send-otp"),
    path("verify-otp/", VerifyOTPView.as_view(), name="verify-otp"),
    path("link-approval/", LinkApprove.as_view(), name="link-approval"),
    path("link-request/", LinkRequestCreate.as_view(), name="link-request-create"),
    path("register-manger/", RegisterRManager.as_view(), name="register-rmanager"),
    path("register-user/", RegisterCustomer.as_view(), name="register-user"),
    path("oauth/exchange/", OAuthExchangeView.as_view(), name="oauth-exchange"),
    path("profile/", UserProfileView.as_view(), name="user-profile"),
    path("profile/delete/", DeleteAccountView.as_view(), name="user-delete"),
    path("", include(token_urls)),
]
