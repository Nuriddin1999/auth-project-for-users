"""
Django settings for the auth project.

All secrets and provider credentials are read from environment variables
(see .env.example). A local `.env` file is loaded automatically.
"""

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')


def env_list(name, default=''):
    return [item.strip() for item in os.getenv(name, default).split(',') if item.strip()]


SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-dev-only-change-me')
DEBUG = os.getenv('DJANGO_DEBUG', 'True').lower() in ('1', 'true', 'yes')
ALLOWED_HOSTS = env_list('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1')


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'rest_framework',
    'rest_framework_simplejwt.token_blacklist',
    'accounts',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# --- CORS ---------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env_list('CORS_ALLOWED_ORIGINS', 'http://localhost:5173')
# Needed so the browser sends/accepts the httpOnly refresh cookie on cross-origin calls.
CORS_ALLOW_CREDENTIALS = True


# --- DRF + JWT ----------------------------------------------------------
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': ('rest_framework.permissions.IsAuthenticated',),
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
}

# Refresh token is stored only in this httpOnly cookie (see accounts/cookies.py).
AUTH_REFRESH_COOKIE_NAME = 'refresh_token'
AUTH_REFRESH_COOKIE_PATH = '/api/auth/'
AUTH_REFRESH_COOKIE_SAMESITE = 'Lax'
AUTH_REFRESH_COOKIE_SECURE = not DEBUG  # HTTPS-only outside local development


# --- Social providers ---------------------------------------------------
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID', '')

FACEBOOK_APP_ID = os.getenv('FACEBOOK_APP_ID', '')
FACEBOOK_APP_SECRET = os.getenv('FACEBOOK_APP_SECRET', '')
FACEBOOK_GRAPH_VERSION = os.getenv('FACEBOOK_GRAPH_VERSION', 'v21.0')

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
# Telegram login payloads older than this (seconds) are rejected (replay protection).
TELEGRAM_AUTH_MAX_AGE = int(os.getenv('TELEGRAM_AUTH_MAX_AGE', '86400'))

# --- Email sign-up / sign-in (one-time codes) ---------------------------
EMAIL_CODE_TTL = int(os.getenv('EMAIL_CODE_TTL') or 60)  # seconds a code stays valid
EMAIL_CODE_LENGTH = 6
# Development only (ignored unless DEBUG): every code is this value and no email is sent.
# Lets you sign up without a working SMTP server. Example: EMAIL_TEST_CODE=12345
EMAIL_TEST_CODE = os.getenv('EMAIL_TEST_CODE', '').strip()
EMAIL_CODE_RESEND_COOLDOWN = 60  # seconds before a new code can be requested
EMAIL_CODE_MAX_PER_HOUR = 5  # codes per email address per hour
EMAIL_CODE_MAX_ATTEMPTS = 5  # wrong guesses before a code is burned

# Without EMAIL_HOST, emails are printed to the runserver console (development).
_smtp_host = os.getenv('EMAIL_HOST', '')
_smtp_user = os.getenv('EMAIL_HOST_USER', '')
# Most providers (Gmail, Yandex, Mail.ru) require "From" to be the authenticated account.
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL') or (
    f'Auth <{_smtp_user}>' if _smtp_user else 'Auth <no-reply@localhost>'
)

if _smtp_host:
    _ssl = os.getenv('EMAIL_USE_SSL', 'False').lower() in ('1', 'true', 'yes')
    MAILERS = {
        'default': {
            'BACKEND': 'django.core.mail.backends.smtp.EmailBackend',
            'OPTIONS': {
                'host': _smtp_host,
                'port': int(os.getenv('EMAIL_PORT') or (465 if _ssl else 587)),
                'username': _smtp_user,
                'password': os.getenv('EMAIL_HOST_PASSWORD', ''),
                'use_ssl': _ssl,  # port 465
                'use_tls': not _ssl
                and os.getenv('EMAIL_USE_TLS', 'True').lower() in ('1', 'true', 'yes'),  # 587
                'timeout': 10,  # don't hang the request if the SMTP server is slow
            },
        },
    }
else:
    MAILERS = {'default': {'BACKEND': 'django.core.mail.backends.console.EmailBackend'}}


# Test mode: accept {"mock": true} on the login endpoints and sign in fake users
# WITHOUT contacting the providers. Only ever active together with DEBUG.
SOCIAL_AUTH_MOCK = DEBUG and os.getenv('SOCIAL_AUTH_MOCK', 'False').lower() in ('1', 'true', 'yes')
# Code that "confirms" a social login in test mode (nothing is really sent).
SOCIAL_AUTH_MOCK_CODE = os.getenv('SOCIAL_AUTH_MOCK_CODE') or '12345'
