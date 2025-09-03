from django.urls import path
from .views import (
    SendOTPView, VerifyOTPView,
    OAuthExchangeView
)

urlpatterns = [
    path("send-otp/", SendOTPView.as_view(), name="send-otp"),
    path("verify-otp/", VerifyOTPView.as_view(), name="verify-otp"),
    # path("register-user/", RegisterUser.as_view(), name="register-user"),
    path("oauth/exchange/", OAuthExchangeView.as_view(), name="oauth-exchange"),
]
