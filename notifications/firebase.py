import json

import firebase_admin
from firebase_admin import credentials
from django.conf import settings


def get_firebase_app():
    if firebase_admin._apps:
        return firebase_admin.get_app()

    if settings.FIREBASE_CREDENTIALS_JSON:
        credentials_data = json.loads(settings.FIREBASE_CREDENTIALS_JSON)
        cred = credentials.Certificate(credentials_data)
    elif settings.FIREBASE_CREDENTIALS_PATH:
        cred = credentials.Certificate(
            settings.FIREBASE_CREDENTIALS_PATH
        )
    else:
        raise RuntimeError(
            "Firebase credentials are not configured. "
            "Set FIREBASE_CREDENTIALS_JSON or "
            "FIREBASE_CREDENTIALS_PATH."
        )

    return firebase_admin.initialize_app(cred)


firebase_app = get_firebase_app()