from . import blocks
from .base import render_shell


def build(context: dict) -> tuple[str, str]:
    """
    Required context keys: product_name, website_url, user_name,
                            order_number, order_total
    Optional: logo_url, support_email, order_date, items (list[str]),
              cta_url, cta_text
    Returns (subject, html_body).
    """
    product_name = context["product_name"]
    user_name = context["user_name"]
    order_number = context["order_number"]
    order_total = context["order_total"]

    content = (
        blocks.heading(f"Thanks for your order, {user_name}!")
        + blocks.paragraph(
            "We've received your order and we're getting it ready. "
            "Here's a quick summary:"
        )
    )

    rows = [("Order #", order_number), ("Total", order_total)]
    if context.get("order_date"):
        rows.append(("Date", context["order_date"]))
    content += blocks.highlight_box(rows)

    if context.get("items"):
        content += blocks.bullet_list(context["items"])

    cta_url = context.get("cta_url")
    if cta_url:
        content += blocks.button(context.get("cta_text", "View your order"), cta_url)

    content += blocks.paragraph(
        f"Questions about your order? Just reply to this email or reach "
        f"out to {context.get('support_email', 'our support team')}.",
        muted=True,
    )

    html = render_shell(
        product_name=product_name,
        website_url=context["website_url"],
        content_html=content,
        logo_url=context.get("logo_url", ""),
        support_email=context.get("support_email", ""),
    )

    subject = f"Thanks for your order — {product_name}"
    return subject, html
