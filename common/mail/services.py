"""
Service layer for outgoing transactional emails.

Usage:
    from .services import send_templated_email, send_otp_email, \\
        send_welcome_email, send_order_thankyou_email, send_congrats_email

    # generic — works for any registered template
    send_templated_email(
        to="user@example.com",
        template_name="congrats",
        context={"user_name": "Ada", "message": "You hit 100 followers!"},
    )

    # convenience wrappers for the common cases
    send_otp_email(email: str, name: str code="482913")
    send_welcome_email(user)
    send_order_thankyou_email(email: str, name: str order_number="A1029", order_total="$42.00")
    send_congrats_email(email: str, name: str message="You've unlocked the Pro plan!")
"""

from django.conf import settings
from django.core.mail import EmailMessage

from .exceptions import EmailDeliveryError
from .router import EmailRouter
from .templates import build_email


def _brand_context() -> dict:
    """
    Site-wide defaults, pulled from Django settings so callers don't have
    to repeat product_name / website_url / logo_url / support_email on
    every call. Override any of these per-call via `context`.
    """
    branding = getattr(settings, "EMAIL_BRANDING", {})
    return {
        "product_name": branding.get("PRODUCT_NAME", getattr(settings, "SITE_NAME", "Our App")),
        "website_url": branding.get("WEBSITE_URL", getattr(settings, "WEBSITE_URL", "")),
        "logo_url": branding.get("LOGO_URL", getattr(settings, "WEBSITE_LOGO_URL", "")),
        "support_email": branding.get("SUPPORT_EMAIL", getattr(settings, "DEFAULT_FROM_EMAIL", "")),
    }


def send_templated_email(to, template_name: str, context: dict, from_email: str | None = None) -> dict:
    """
    Build `template_name` with `context` (merged over brand defaults) and
    send it through the EmailRouter (which handles multi-provider failover).

    `to` can be a single address or a list of addresses.
    Returns the dict from EmailRouter.send(): {"success": bool, ...}.
    Raises EmailDeliveryError if all providers fail.
    """
    full_context = {**_brand_context(), **context}
    subject, html_body = build_email(template_name, full_context)

    recipients = [to] if isinstance(to, str) else list(to)

    message = EmailMessage(
        subject=subject,
        body=html_body,
        to=recipients,
        from_email=from_email or getattr(settings, "DEFAULT_FROM_EMAIL", None),
    )
    message.content_subtype = "html"

    result = EmailRouter().send(message)

    if not result.get("success"):
        raise EmailDeliveryError(result.get("error", "All email providers failed"))

    return result


def send_email(message):
    """Low-level escape hatch: send a pre-built EmailMessage directly."""
    return EmailRouter().send(message)


# ---------------------------------------------------------------------
# Convenience wrappers for the common email types
# ---------------------------------------------------------------------

def send_otp_email(email:str, code: str, minutes_valid: int = 10) -> dict:
    return send_templated_email(
        to=email,
        template_name="otp",
        context={"code": code, "minutes_valid": minutes_valid},
    )


def send_welcome_email(email: str, name: str| None = None, cta_url: str | None = None, cta_text: str = "Get started") -> dict:
    return send_templated_email(
        to=email,
        template_name="welcome",
        context={
            "user_name": name or email,
            "cta_url": cta_url,
            "cta_text": cta_text,
        },
    )


def send_order_thankyou_email(
    email: str,
    order_number: str,
    order_total: str,
    name: str| None = None,
    order_date: str | None = None,
    items: list[str] | None = None,
    cta_url: str | None = None,
) -> dict:
    return send_templated_email(
        to=email,
        template_name="order_thankyou",
        context={
            "user_name": name or email,
            "order_number": order_number,
            "order_total": order_total,
            "order_date": order_date,
            "items": items,
            "cta_url": cta_url,
        },
    )


def send_congrats_email(
    email: str,
    message: str,
    name: str| None = None,
    title: str = "Congratulations!",
    cta_url: str | None = None,
    cta_text: str = "Take a look",
) -> dict:
    return send_templated_email(
        to=email,
        template_name="congrats",
        context={
            "user_name": name or email,
            "message": message,
            "title": title,
            "cta_url": cta_url,
            "cta_text": cta_text,
        },
    )
