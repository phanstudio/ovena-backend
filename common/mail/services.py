from django.core.mail import EmailMessage
from .router import EmailRouter


def send_otp_email(user, code):

    message = EmailMessage(
        subject="Your OTP Code",
        body=f"Your code is {code}",
        to=[user.email],
    )

    return EmailRouter().send(message)


def send_email(message):
    return EmailRouter().send(message)


# email replacement
# html_body = f"""
# <!doctype html>
# <html>
#   <body style="margin:0;padding:0;background:#f6f7fb;font-family:Arial,sans-serif;">
#     <div style="max-width:560px;margin:0 auto;padding:24px;">
#       <div style="background:#ffffff;border-radius:14px;padding:24px;border:1px solid #e8e9ee;">
#         {"<div style='text-align:center;margin-bottom:16px;'><img src='"+logo_url+"' alt='"+product_name+"' style='height:36px;'/></div>" if logo_url else ""}
#         <h2 style="margin:0 0 12px 0;color:#111827;font-size:20px;">Hi!</h2>
#         <p style="margin:0 0 14px 0;color:#374151;font-size:14px;line-height:1.5;">
#           Use the following one-time password (OTP) to sign in to your {product_name} account.
#         </p>

#         <div style="background:#f3f4f6;border:1px solid #e5e7eb;border-radius:12px;padding:18px;text-align:center;margin:18px 0;">
#           <div style="font-size:28px;letter-spacing:6px;font-weight:700;color:#111827;">{code}</div>
#         </div>

#         <p style="margin:0 0 12px 0;color:#374151;font-size:13px;line-height:1.5;">
#           This OTP will be valid for <b>{minutes_valid} minutes</b> till
#           <b>{expires_str}</b> ({tz_str}).
#         </p>

#         <p style="margin:0 0 18px 0;color:#6b7280;font-size:12px;line-height:1.5;">
#           If you didn't request this, you can safely ignore this email.
#         </p>

#         <hr style="border:none;border-top:1px solid #e5e7eb;margin:18px 0;" />

#         <p style="margin:0;color:#6b7280;font-size:12px;line-height:1.5;">
#           Need help? Contact <a href="mailto:{support_email}" style="color:#2563eb;text-decoration:none;">{support_email}</a><br/>
#           <a href="{website_url}" style="color:#2563eb;text-decoration:none;">{website_url}</a>
#         </p>
#       </div>

#       <p style="text-align:center;color:#9ca3af;font-size:11px;margin:14px 0 0 0;">
#         © {product_name}. All rights reserved.
#       </p>
#     </div>
#   </body>
# </html>
# """