from . import blocks
from .base import render_shell


def build(context: dict) -> tuple[str, str]:
    """
    Required context keys: product_name, website_url, code, minutes_valid
    Optional: logo_url, support_email
    Returns (subject, html_body).
    """
    product_name = context["product_name"]
    minutes_valid = context["minutes_valid"]
    code = context["code"]

    content = (
        blocks.heading("Help us protect your account")
        + blocks.paragraph(
            "Before you sign in, we need to verify your identity. "
            "Enter the following code on the sign-in page."
        )
        + blocks.code_block(code)
        + blocks.paragraph(
            f"If you have not recently tried to sign into {product_name}, "
            "we recommend changing your password and setting up "
            "Two-Factor Authentication to keep your account safe. "
            f"Your verification code expires after {minutes_valid} minutes.",
            muted=True,
        )
    )

    html = render_shell(
        product_name=product_name,
        website_url=context["website_url"],
        content_html=content,
        logo_url=context.get("logo_url", ""),
        support_email=context.get("support_email", ""),
    )

    subject = f"Your {product_name} verification code"
    return subject, html
