from . import blocks
from .base import render_shell


def build(context: dict) -> tuple[str, str]:
    """
    Required context keys: product_name, website_url, alert_type, message
    Optional: logo_url, support_email, user_name, ip_address, timestamp
    Returns (subject, html_body).
    """
    product_name = context["product_name"]
    alert_type = context.get("alert_type", "suspicious_activity")
    message = context.get("message", "Suspicious activity was detected on your account.")
    user_name = context.get("user_name", "User")
    ip_address = context.get("ip_address")

    title = "Security Alert: Suspicious Activity Detected"
    if alert_type == "pin_lockout":
        title = "Security Alert: Transaction PIN Locked"
    elif alert_type == "credential_change":
        title = "Security Alert: Sensitive Details Updated"
    elif alert_type == "withdrawal_flagged":
        title = "Security Alert: Withdrawal Flagged for Compliance Review"

    content = (
        blocks.heading(title)
        + blocks.paragraph(f"Hello {user_name},")
        + blocks.paragraph(message)
    )

    if ip_address:
        content += blocks.paragraph(f"Action IP Address: {ip_address}", muted=True)

    content += blocks.paragraph(
        f"If you did not initiate this action, please contact {product_name} support immediately "
        "to secure your account.",
        muted=True,
    )

    html = render_shell(
        product_name=product_name,
        website_url=context["website_url"],
        content_html=content,
        logo_url=context.get("logo_url", ""),
        support_email=context.get("support_email", ""),
    )

    subject = f"[{product_name} Security Alert] {title}"
    return subject, html
