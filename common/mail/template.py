
def maling_temp(product_name, website_url, logo_url, support_email, minutes_valid, code):
    html_body = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    /* Mobile-first responsive styles */
    @media only screen and (max-width: 600px) {{
      .container {{
        width: 100% !important;
        max-width: 100% !important;
      }}
      .wrapper {{
        width: 100% !important;
        max-width: 100% !important;
        border-radius: 0 !important;
        border-left: none !important;
        border-right: none !important;
      }}
      .wrapper-cell {{
        padding: 18px 15px !important;
      }}
      .content {{
        max-width: 100% !important;
        padding: 0 10px !important;
      }}
      .code-block {{
        width: auto !important;
        min-width: 160px !important;
        padding: 0 20px !important;
        font-size: 1.8em !important;
        height: 50px !important;
        line-height: 50px !important;
      }}
      h3 {{
        font-size: 1.2em !important;
      }}
      p {{
        font-size: 0.9em !important;
      }}
      .footer-text {{
        font-size: 12px !important;
      }}
      .footer-logo {{
        width: 70px !important;
      }}
    }}
  </style>
</head>
<body style="margin:0;padding:0;background:#fafafa;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#fafafa" style="background:#fafafa;margin:0;padding:0;">
    <tr>
      <td align="center" style="padding:0;">
        <!-- Main container: max-width 640px, centered -->
        <table class="container" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:640px;margin:0 auto;background:#fafafa;border-collapse:collapse;">
          <tr>
            <!-- Top purple bar -->
            <td style="height:4px;font-size:4px;line-height:4px;background:#6b4fbb;" bgcolor="#6b4fbb"></td>
          </tr>
          <tr>
            <!-- Logo (top) -->
            <td align="center" style="padding:25px 0;font-size:13px;line-height:1.6;color:#5c5c5c;">
              {"<img alt='" + product_name + "' src='" + logo_url + "' width='55' height='55' style='max-width:55px;height:auto;'>" if logo_url else "<span style='font-size:24px;font-weight:bold;color:#303030;'>" + product_name + "</span>"}
            </td>
          </tr>
          <tr>
            <td align="center" style="padding:0 10px;">
              <!-- White card wrapper -->
              <table class="wrapper" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:640px;margin:0 auto;border-collapse:separate;border-spacing:0;border-radius:3px;border:1px solid #ededed;background:#ffffff;" bgcolor="#ffffff">
                <tr>
                  <td class="wrapper-cell" style="padding:18px 25px;border-radius:3px;background:#ffffff;" bgcolor="#ffffff">
                    <!-- Content -->
                    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:separate;border-spacing:0;">
                      <tr>
                        <td>
                          <div class="content" style="max-width:400px;margin:0 auto;color:#1f1f1f;line-height:1.25em;text-align:center;">
                            <h3 style="font-size:1.3em;font-weight:500;margin:0 0 0.5em;">Help us protect your account</h3>
                            <p style="font-size:0.9em;margin:0 0 1.5em;">
                              Before you sign in, we need to verify your identity.
                              Enter the following code on the sign-in page.
                            </p>
                            <!-- Code block - fluid width -->
                            <div class="code-block" style="display:inline-block;min-width:207px;height:53px;line-height:53px;background:#f0f0f0;font-weight:700;font-size:1.5em;color:#303030;margin:26px auto;border-radius:3px;letter-spacing:2px;padding:0 20px;text-align:center;">
                              {code}
                            </div>
                            <p style="font-size:0.75em;color:#5c5c5c;margin:1.5em 0 0;">
                              If you have not recently tried to sign into {product_name},
                              we recommend changing your password and setting up
                              Two-Factor Authentication to keep your account safe.
                              Your verification code expires after {minutes_valid} minutes.
                            </p>
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
            <!-- Footer -->
            <td align="center" style="padding:25px 10px;font-size:13px;line-height:1.6;color:#5c5c5c;">
              {"<img alt='" + product_name + "' src='" + logo_url + "' class='footer-logo' style='display:block;width:90px;max-width:90px;height:auto;margin:0 auto 1em;'>" if logo_url else ""}
              <div class="footer-text" style="font-size:13px;">
                You're receiving this email because of your account on
                <a href="{website_url}" style="color:#3777b0;text-decoration:none;">{website_url}</a>.
                <a href="{website_url}/-/profile/notifications" style="color:#3777b0;text-decoration:none;">Manage all notifications</a> ·
                <a href="{website_url}/help" style="color:#3777b0;text-decoration:none;">Help</a>
              </div>
              <div style="margin-top:1em;font-size:12px;color:#aaa;">
                <a href="mailto:{support_email}" style="color:#3777b0;text-decoration:none;">{support_email}</a>
              </div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""
    return  html_body
