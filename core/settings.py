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

# Application definition
INSTALLED_APPS = [
    "daphne",
    "channels",
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.gis',    
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_gis',
    "drf_spectacular",
    "drf_spectacular_sidecar",
    'corsheaders',
    'accounts',
    'addresses',
    'menu',
    'authflow',
    'ratings',
    'coupons_discount',
    # 'anymail',
]


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
            "hosts": [os.environ["REDIS_URL"]],  # <-- Use full URL
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

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',},
]

# TIMEZONE & LANGUAGE
LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", default="UTC")
USE_I18N = True
USE_TZ = True

# STATIC & MEDIA
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
