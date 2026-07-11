from django.core.mail import EmailMessage
from .router import EmailRouter


def send_otp_email(user, code):

    message = EmailMessage(
        subject="Your OTP Code",
        body=f"Your code is {code}",
        to=[user.email],
    )

    return EmailRouter().send(message)


def send_email(message):
    return EmailRouter().send(message)
