"""
Shared responsive HTML shell for all outgoing emails.

Every concrete template (OTP, welcome, order thank-you, congrats, ...)
builds a small chunk of `content_html` and passes it here. This file
owns the layout: purple top bar, logo, white card, footer. Change the
look once here and every email type picks it up.
"""


def render_shell(
    product_name: str,
    website_url: str,
    content_html: str,
    logo_url: str = "",
    support_email: str = "",
    accent_color: str = "#6b4fbb",
) -> str:
    """
    Wraps `content_html` in the standard branded email layout.

    content_html: pre-built inner HTML (title, paragraphs, code block,
                  button, etc). Build it with helpers from `blocks.py`.
    """
    logo_header = (
        f"<img alt='{product_name}' src='{logo_url}' width='55' height='55' "
        f"style='max-width:55px;height:auto;'>"
        if logo_url
        else f"<span style='font-size:24px;font-weight:bold;color:#303030;'>{product_name}</span>"
    )

    logo_footer = (
        f"<img alt='{product_name}' src='{logo_url}' class='footer-logo' "
        f"style='display:block;width:90px;max-width:90px;height:auto;margin:0 auto 1em;'>"
        if logo_url
        else ""
    )

    support_block = (
        f"""<div style="margin-top:1em;font-size:12px;color:#aaa;">
              <a href="mailto:{support_email}" style="color:#3777b0;text-decoration:none;">{support_email}</a>
            </div>"""
        if support_email
        else ""
    )

    return f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    @media only screen and (max-width: 600px) {{
      .container {{ width: 100% !important; max-width: 100% !important; }}
      .wrapper {{
        width: 100% !important; max-width: 100% !important;
        border-radius: 0 !important; border-left: none !important; border-right: none !important;
      }}
      .wrapper-cell {{ padding: 18px 15px !important; }}
      .content {{ max-width: 100% !important; padding: 0 10px !important; }}
      .code-block {{
        width: auto !important; min-width: 160px !important; padding: 0 20px !important;
        font-size: 1.8em !important; height: 50px !important; line-height: 50px !important;
      }}
      h3 {{ font-size: 1.2em !important; }}
      p {{ font-size: 0.9em !important; }}
      .footer-text {{ font-size: 12px !important; }}
      .footer-logo {{ width: 70px !important; }}
    }}
  </style>
</head>
<body style="margin:0;padding:0;background:#fafafa;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#fafafa" style="background:#fafafa;margin:0;padding:0;">
    <tr>
      <td align="center" style="padding:0;">
        <table class="container" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:640px;margin:0 auto;background:#fafafa;border-collapse:collapse;">
          <tr>
            <td style="height:4px;font-size:4px;line-height:4px;background:{accent_color};" bgcolor="{accent_color}"></td>
          </tr>
          <tr>
            <td align="center" style="padding:25px 0;font-size:13px;line-height:1.6;color:#5c5c5c;">
              {logo_header}
            </td>
          </tr>
          <tr>
            <td align="center" style="padding:0 10px;">
              <table class="wrapper" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:640px;margin:0 auto;border-collapse:separate;border-spacing:0;border-radius:3px;border:1px solid #ededed;background:#ffffff;" bgcolor="#ffffff">
                <tr>
                  <td class="wrapper-cell" style="padding:18px 25px;border-radius:3px;background:#ffffff;" bgcolor="#ffffff">
                    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:separate;border-spacing:0;">
                      <tr>
                        <td>
                          <div class="content" style="max-width:420px;margin:0 auto;color:#1f1f1f;line-height:1.25em;text-align:center;">
                            {content_html}
                          </div>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td align="center" style="padding:25px 10px;font-size:13px;line-height:1.6;color:#5c5c5c;">
              {logo_footer}
              <div class="footer-text" style="font-size:13px;">
                You're receiving this email because of your account on
                <a href="{website_url}" style="color:#3777b0;text-decoration:none;">{website_url}</a>.
                <a href="{website_url}/-/profile/notifications" style="color:#3777b0;text-decoration:none;">Manage all notifications</a> ·
                <a href="{website_url}/help" style="color:#3777b0;text-decoration:none;">Help</a>
              </div>
              {support_block}
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""
