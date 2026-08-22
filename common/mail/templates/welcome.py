from . import blocks
from .base import render_shell


def build(context: dict) -> tuple[str, str]:
    """
    Required context keys: product_name, website_url, user_name
    Optional: logo_url, support_email, cta_url, cta_text
    Returns (subject, html_body).
    """
    product_name = context["product_name"]
    user_name = context["user_name"]

    content = (
        blocks.heading(f"Welcome to {product_name}, {user_name}!")
        + blocks.paragraph(
            f"Thanks for signing up. We're glad you're here — your account "
            f"is ready to go and there's nothing else you need to do."
        )
    )

    cta_url = context.get("cta_url")
    if cta_url:
        content += blocks.button(context.get("cta_text", "Get started"), cta_url)

    content += blocks.paragraph(
        "If you didn't create this account, you can safely ignore this email.",
        muted=True,
    )

    html = render_shell(
        product_name=product_name,
        website_url=context["website_url"],
        content_html=content,
        logo_url=context.get("logo_url", ""),
        support_email=context.get("support_email", ""),
    )

    subject = f"Welcome to {product_name}!"
    return subject, html
