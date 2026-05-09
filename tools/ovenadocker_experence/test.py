# Django backend auth example: SMS OTP + JWT and OAuth2 (Google + Apple via PKCE)
# Project structure (single-file presentation):
# - project/settings.py
# - project/urls.py
# - authapp/models.py
# - authapp/serializers.py
# - authapp/views.py
# - authapp/urls.py
# - authapp/services.py
# - requirements.txt

########################################################################
# project/settings.py
########################################################################

########################################################################
# project/urls.py
########################################################################

########################################################################
# authapp/models.py
########################################################################

########################################################################
# authapp/serializers.py
########################################################################

########################################################################
# authapp/services.py
########################################################################

########################################################################
# authapp/views.py
########################################################################

########################################################################
# authapp/urls.py
########################################################################

########################################################################
# requirements.txt
########################################################################

########################################################################
# Notes & TODOs
########################################################################

# 1) Apple: you must generate a client secret JWT signed with your Apple key (private key) per Apple's docs.
#    That JWT is used as client_secret for token exchange. Libraries exist to help build it.

# 2) PKCE: On mobile, the app should generate code_verifier and code_challenge and include
#    the code_challenge in the authorization request. The app receives the code and passes code_verifier
#    to the backend which forwards it to the provider during token exchange (or backend can store it —
#    but passing from app to backend is fine over TLS).

# 3) Security: only accept authorization codes from your app (use redirect URI checks). Ensure HTTPS.

# 4) For production: set DEBUG=False, use proper ALLOWED_HOSTS, configure database, configure CORS, rate-limiting, logging.

# 5) You may want to persist external provider ids (sub) and provider names to link accounts to users.

# 6) Tests and migrations are not included; make migrations for authapp and run migrate.

# 7) Example mobile flow (React Native):
#    - App opens provider auth (Google/Apple) with PKCE. Provider returns code to the app.
#    - App POSTs {provider, code, code_verifier} to /api/auth/oauth/exchange/.
#    - Backend exchanges code securely, creates/returns JWT tokens to the app.

# End of file
