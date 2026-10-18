import json
import logging

import firebase_admin
from firebase_admin import credentials
from django.conf import settings

logger = logging.getLogger(__name__)


def get_firebase_app():
    if firebase_admin._apps:
        return firebase_admin.get_app()

    json_creds = getattr(settings, "FIREBASE_CREDENTIALS_JSON", None)
    path = getattr(settings, "FIREBASE_CREDENTIALS_PATH", None)

    if json_creds:
        cred = credentials.Certificate(json.loads(json_creds))
    elif path:
        cred = credentials.Certificate(path)
    else:
        if settings.DEBUG:
            logger.warning("Firebase credentials not configured; skipping init.")
            return None
        raise RuntimeError(
            "Set FIREBASE_CREDENTIALS_JSON or FIREBASE_CREDENTIALS_PATH."
        )

    return firebase_admin.initialize_app(cred)


firebase_app = get_firebase_app()