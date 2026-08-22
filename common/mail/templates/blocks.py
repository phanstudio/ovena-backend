"""
Small, composable HTML fragments used to build the inner `content_html`
that gets passed into `base.render_shell`. Mix and match per template
instead of duplicating markup in every template file.
"""

from typing import Iterable, Optional, Sequence, Tuple


def heading(text: str) -> str:
    return f'<h3 style="font-size:1.3em;font-weight:500;margin:0 0 0.5em;">{text}</h3>'


def paragraph(text: str, muted: bool = False) -> str:
    color = "color:#5c5c5c;" if muted else ""
    size = "font-size:0.75em;" if muted else "font-size:0.9em;"
    return f'<p style="{size}{color}margin:0 0 1.5em;">{text}</p>'


def code_block(code: str) -> str:
    return f"""<div class="code-block" style="display:inline-block;min-width:207px;height:53px;
        line-height:53px;background:#f0f0f0;font-weight:700;font-size:1.5em;color:#303030;
        margin:26px auto;border-radius:3px;letter-spacing:2px;padding:0 20px;text-align:center;">
        {code}
    </div>"""


def button(text: str, url: str, accent_color: str = "#6b4fbb") -> str:
    return f"""<div style="margin:26px auto;">
        <a href="{url}" style="background:{accent_color};color:#ffffff;text-decoration:none;
            display:inline-block;padding:12px 28px;border-radius:4px;font-weight:600;font-size:0.95em;">
            {text}
        </a>
    </div>"""


def highlight_box(rows: Sequence[Tuple[str, str]]) -> str:
    """
    A bordered key/value box — handy for order number, amount, date, etc.
    rows: [("Order #", "12345"), ("Total", "$42.00")]
    """
    row_html = "".join(
        f"""<tr>
              <td style="padding:6px 0;color:#5c5c5c;font-size:0.85em;text-align:left;">{label}</td>
              <td style="padding:6px 0;color:#1f1f1f;font-size:0.85em;text-align:right;font-weight:600;">{value}</td>
            </tr>"""
        for label, value in rows
    )
    return f"""<table width="100%" cellpadding="0" cellspacing="0" border="0"
        style="margin:20px 0;border:1px solid #ededed;border-radius:3px;padding:12px 16px;">
        {row_html}
    </table>"""


def bullet_list(items: Iterable[str]) -> str:
    lis = "".join(f'<li style="margin:0 0 0.4em;">{item}</li>' for item in items)
    return f'<ul style="text-align:left;font-size:0.85em;color:#5c5c5c;margin:0 0 1.5em;padding-left:1.2em;">{lis}</ul>'
