from django.conf import settings
from anymail.backends.resend import EmailBackend as ResendBackend
# from anymail.backends.brevo import EmailBackend as BrevoBackend
from typing import List
from anymail.backends.base import AnymailBaseBackend


def get_email_providers() -> List[tuple[str, AnymailBaseBackend]]:
    return [
        (
            "resend",
            ResendBackend(
                api_key=settings.ANYMAIL["RESEND_API_KEY"]
            ),
        ),
        # (
        #     "brevo",
        #     BrevoBackend(
        #         api_key=settings.ANYMAIL["BREVO_API_KEY"]
        #     ),
        # ),
    ]
