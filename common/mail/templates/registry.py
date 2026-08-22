"""
Central lookup of every available email template.

To add a new email type: write a new module in this package exposing
`build(context: dict) -> tuple[subject, html]`, then register it here.
Nothing else in the app needs to change.
"""

from . import congrats, order_thankyou, otp, welcome

TEMPLATES = {
    "otp": otp.build,
    "welcome": welcome.build,
    "order_thankyou": order_thankyou.build,
    "congrats": congrats.build,
}


def build_email(template_name: str, context: dict) -> tuple[str, str]:
    """
    Look up a template by name and render it.
    Raises KeyError with a helpful message if the template doesn't exist.
    """
    try:
        builder = TEMPLATES[template_name]
    except KeyError:
        available = ", ".join(sorted(TEMPLATES))
        raise KeyError(
            f"Unknown email template '{template_name}'. Available: {available}"
        )
    return builder(context)
