import json

import firebase_admin
from firebase_admin import credentials
from django.conf import settings


import os
import logging

logger = logging.getLogger(__name__)


def get_firebase_app():
    if firebase_admin._apps:
        return firebase_admin.get_app()

    try:
        if getattr(settings, "FIREBASE_CREDENTIALS_JSON", None):
            credentials_data = json.loads(settings.FIREBASE_CREDENTIALS_JSON)
            cred = credentials.Certificate(credentials_data)
            return firebase_admin.initialize_app(cred)
        elif getattr(settings, "FIREBASE_CREDENTIALS_PATH", None) and os.path.exists(settings.FIREBASE_CREDENTIALS_PATH):
            cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
            return firebase_admin.initialize_app(cred)
        else:
            logger.warning("Firebase credentials not found or unconfigured. Notifications app running without Firebase.")
            return None
    except Exception as e:
        logger.warning("Firebase initialization failed: %s", e)
        return None


firebase_app = get_firebase_app()