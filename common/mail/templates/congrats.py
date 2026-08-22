from . import blocks
from .base import render_shell


def build(context: dict) -> tuple[str, str]:
    """
    Required context keys: product_name, website_url, user_name, message
    Optional: logo_url, support_email, title, cta_url, cta_text

    `message` is the main congratulatory paragraph (e.g. "You've completed
    your first course!", "You've been upgraded to Pro!").
    """
    product_name = context["product_name"]
    user_name = context["user_name"]
    title = context.get("title", "Congratulations!")

    content = (
        blocks.heading(f"{title} {user_name} 🎉")
        + blocks.paragraph(context["message"])
    )

    cta_url = context.get("cta_url")
    if cta_url:
        content += blocks.button(context.get("cta_text", "Take a look"), cta_url)

    html = render_shell(
        product_name=product_name,
        website_url=context["website_url"],
        content_html=content,
        logo_url=context.get("logo_url", ""),
        support_email=context.get("support_email", ""),
    )

    subject = context.get("subject", f"{title.rstrip('!')} — {product_name}")
    return subject, html
