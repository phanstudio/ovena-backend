import os
import environ
from pathlib import Path
from datetime import timedelta
import sys

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Initialise environ
env = environ.Env(
    # default types + values
    DEBUG=(bool, False)
)

# Read .env file (optional if using system env)
environ.Env.read_env(os.path.join(BASE_DIR, ".env"))

if os.name == 'posix':  # Linux / macOS
    VENV_BASE = os.environ.get("VIRTUAL_ENV", "/opt/venv")
    PY_VERSION = f"python{sys.version_info.major}.{sys.version_info.minor}"

    OS_GEO_PATH = os.path.join(VENV_BASE, "lib", PY_VERSION, "site-packages", "osgeo")
    PROJ_PATH = os.path.join(OS_GEO_PATH, "data", "proj")

    os.environ["PATH"] = OS_GEO_PATH + ":" + os.environ.get("PATH", "")
    os.environ["PROJ_LIB"] = PROJ_PATH

# SECURITY
SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])


# APPS
# ------------------------------------------------------------------------------
DJANGO_APPS = [
    "daphne",
    "channels",
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.gis',
]
THIRD_PARTY_APPS = [
    # "allauth",
    # "allauth.account",
    # "allauth.mfa",
    # "allauth.socialaccount",
    # "django_celery_beat",
    # "rest_framework.authtoken",
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_gis',
    "drf_spectacular",
    "drf_spectacular_sidecar",
    'corsheaders',
    "anymail",
]

LOCAL_APPS = [
    # "ovena.users",
    'accounts',
    'addresses',
    'menu',
    'authflow',
    'ratings',
    'coupons_discount',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    "whitenoise.middleware.WhiteNoiseMiddleware",
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    # 'DEFAULT_PERMISSION_CLASSES': (
    #     'rest_framework.permissions.IsAuthenticated',
    # ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(days=7),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}

CUSTOM_TOKEN_LIFETIME = 60*60*24*30 # 30 days like the refreshtoken

CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

# CACHES
CACHES = {
    "default": env.cache("CACHE_URL", default="locmemcache://")
}
REDIS_URL = env("REDIS_URL")

# opt (sms)
TERMII_API_KEY = env("TERMII_API_KEY")
TERMII_BASE_URL = env("TERMII_BASE_URL")
TERMII_SENDER_ID = env("TERMII_SENDER_ID")
MAX_OTP_SENDS = 3
RATE_LIMIT_WINDOW = 600
OTP_EXPIRY = 300

DEFAULT_PAYMENT_EMAIL= env("DEFAULT_EMAIL")

BRANCH_CONFIRMATION_TIMEOUT = 300  # minutes
PAYMENT_TIMEOUT = 300  # minutes

# paystack
PAYSTACK_SECRET_KEY = env("PAYSTACK_SERECT_KEY") # correct change later


DRIVER_SEARCH_RADIUS_KM = [5, 10, 15]
DRIVER_LOCATION_STALE_THRESHOLD = 60*60#60 # seconds

MAX_DRIVERS_TO_NOTIFY = 5
DRIVER_ACCEPTANCE_TIMEOUT = 60 # seconds

# OAuth provider config placeholders
OAUTH_PROVIDERS = {
    "google": {
        "CLIENT_ID": env('GOOGLE_CLIENT_ID'),
        "CLIENT_SECRET": env('GOOGLE_CLIENT_SECRET'),
        "TOKEN_ENDPOINT": "https://oauth2.googleapis.com/token",
        "USERINFO_ENDPOINT": "https://openidconnect.googleapis.com/v1/userinfo",
        "REDIRECT_URI": env('GOOGLE_REDIRECT_URI'), # mobile redirect if used
    },
    # "apple": {
    #     "CLIENT_ID": "com.your.app.bundle-id",
    #     # For Apple you must build a client secret (JWT signed with your Apple key)
    #     "CLIENT_SECRET": "<GENERATED_APPLE_CLIENT_SECRET_JWT>",
    #     "TOKEN_ENDPOINT": "https://appleid.apple.com/auth/token",
    #     "REDIRECT_URI": "com.yourapp:/oauth2redirect/apple",
    # }
}
# Channels configuration
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],  # <-- Use full URL
            "capacity": 1500,
            "expiry": 10,
            "prefix": "ws",
            "group_expiry": 60,
        },
    },
}

# Session engine for WebSocket auth
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

ASGI_APPLICATION = "core.asgi.application"

ROOT_URLCONF = 'core.urls'
WSGI_APPLICATION = 'core.wsgi.application'
AUTH_USER_MODEL = "accounts.User"


CELERY_BROKER_URL = f"{REDIS_URL}/2"
CELERY_RESULT_BACKEND = f"{REDIS_URL}/3"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"

WEBSOCKET_URL = env("WEBSOCKET_URL", default="ws://localhost:8000")

# monitoring
ENABLE_METRICS = env("ENABLE_METRICS", cast=bool, default=False)

if ENABLE_METRICS:
    INSTALLED_APPS += ["django_prometheus"]
    MIDDLEWARE = (
        ["django_prometheus.middleware.PrometheusBeforeMiddleware"]
        + MIDDLEWARE
        + ["django_prometheus.middleware.PrometheusAfterMiddleware"]
    )


# Aws
AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY")
AWS_S3_REGION_NAME = env("DJANGO_AWS_S3_REGION_NAME", default=None)

AWS_PUBLIC_BUCKET_NAME = env("DJANGO_AWS_PUBLIC_BUCKET_NAME")
AWS_PRIVATE_BUCKET_NAME = env("DJANGO_AWS_PRIVATE_BUCKET_NAME")

AWS_PUBLIC_CUSTOM_DOMAIN = env("DJANGO_AWS_PUBLIC_CUSTOM_DOMAIN", default=None)  # e.g. cdn.example.com
AWS_PRIVATE_CUSTOM_DOMAIN = env("DJANGO_AWS_PRIVATE_CUSTOM_DOMAIN", default=None)  # optional, often none

PUBLIC_DOMAIN = AWS_PUBLIC_CUSTOM_DOMAIN or f"{AWS_PUBLIC_BUCKET_NAME}.s3.amazonaws.com"
PRIVATE_DOMAIN = AWS_PRIVATE_CUSTOM_DOMAIN or f"{AWS_PRIVATE_BUCKET_NAME}.s3.amazonaws.com"

_AWS_EXPIRY = 60 * 60 * 24 * 7
AWS_S3_OBJECT_PARAMETERS = {
    "CacheControl": f"max-age={_AWS_EXPIRY}, s-maxage={_AWS_EXPIRY}",
}
# "CacheControl": f"max-age={_AWS_EXPIRY}, s-maxage={_AWS_EXPIRY}, must-revalidate",

AWS_S3_MAX_MEMORY_SIZE = env.int(
    "DJANGO_AWS_S3_MAX_MEMORY_SIZE",
    default=25_000_000,  # 100MB
)

# storage
STORAGES = {
    # keep static in container (Option A)
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },

    # default media (public) - optional: make this public by default
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": AWS_PUBLIC_BUCKET_NAME,
            "location": "media",
            "file_overwrite": False,
            "custom_domain": AWS_PUBLIC_CUSTOM_DOMAIN,  # ok if None
            "querystring_auth": False,  # public URLs
        },
    },

    # private media storage
    "private": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": AWS_PRIVATE_BUCKET_NAME,
            "location": "private",
            "file_overwrite": False,
            "custom_domain": AWS_PRIVATE_CUSTOM_DOMAIN,  # often None
            "querystring_auth": True,  # SIGNED URLs
        },
    },
}

MEDIA_URL = f"https://{PUBLIC_DOMAIN}/media/"


# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases
# Parse the DATABASE_URL first
db_config = env.db()  # returns a dict with ENGINE, NAME, USER, PASSWORD, HOST, PORT

# Override ENGINE for PostGIS
db_config["ENGINE"] = "django.contrib.gis.db.backends.postgis"

# Add additional settings
db_config.update({
    "CONN_MAX_AGE": 60,
    "CONN_HEALTH_CHECKS": True,
    "OPTIONS": {
        "connect_timeout": 3,
        "client_encoding": "UTF8",
    },
    "POOL": {
        "POOL_SIZE": 20,
        "MAX_OVERFLOW": 10,
        "RECYCLE": 300,
    }
})

DATABASES = {
    "default": db_config
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Ovena-food-D API",
    "DESCRIPTION": "API with JWT authentication",
    "VERSION": "1.0.0",
    "SECURITY": [{"BearerAuth": []}],
    "COMPONENTS": {
        "securitySchemes": {
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
            }
        }
    },
}

# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',},
]

EMAIL_BACKEND = "anymail.backends.amazon_ses.EmailBackend"

DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL")
SERVER_EMAIL = env("SERVER_EMAIL")

ANYMAIL = {
    "AMAZON_SES_CLIENT_PARAMS": {
        "aws_access_key_id": AWS_ACCESS_KEY_ID,
        "aws_secret_access_key": AWS_SECRET_ACCESS_KEY,
        "region_name": env("AWS_DEFAULT_REGION"),
    }
}

PRODUCT_NAME = "Newbutt"
WEBSITE_URL = "https://newbutt.buzz/"
EMAIL_LOGO_URL = "https://res.cloudinary.com/daxdh7b3t/image/upload/v1767957815/1f2b751b-cc9a-42cd-a623-05b0febc4472.webp" 

# TIMEZONE & LANGUAGE
LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", default="UTC")
USE_I18N = True
USE_TZ = True

# STATIC & MEDIA
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
