from django.urls import path
from .views import (
    SendOTPView, VerifyOTPView,
    RegisterUser
)

urlpatterns = [
    path("send-otp/", SendOTPView.as_view(), name="send-otp"),
    path("verify-otp/", VerifyOTPView.as_view(), name="verify-otp"),
    path("register-user/", RegisterUser.as_view(), name="register-user"),
]
