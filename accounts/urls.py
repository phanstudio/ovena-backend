from django.urls import path
from .views import (
    SendOTPView, VerifyOTPView,
    OAuthExchangeView, LinkRequestCreate, LinkApprove, RegisterRManager
)

urlpatterns = [
    path("send-otp/", SendOTPView.as_view(), name="send-otp"),
    path("verify-otp/", VerifyOTPView.as_view(), name="verify-otp"),
    path("link-approval/", LinkApprove.as_view(), name="link-approval"),
    path("link-request/", LinkRequestCreate.as_view(), name="link-request-create"),
    path("register-manger/", RegisterRManager.as_view(), name="register-rmanager"),
    # path("register-user/", RegisterUser.as_view(), name="register-user"),
    path("oauth/exchange/", OAuthExchangeView.as_view(), name="oauth-exchange"),
]
