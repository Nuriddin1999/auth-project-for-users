"""
Server-side verification of credentials coming from each provider.

Each verifier returns a normalized `SocialProfile` or raises `ProviderError`.
Never trust profile data sent by the browser: always verify it here.
"""

import hashlib
import hmac
import time
from dataclasses import dataclass, field

import requests
from django.conf import settings
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

HTTP_TIMEOUT = 10


class ProviderError(Exception):
    pass


class ProviderNotConfigured(ProviderError):
    pass


@dataclass
class SocialProfile:
    provider: str
    uid: str
    email: str = ''
    email_verified: bool = False
    first_name: str = ''
    last_name: str = ''
    username_hint: str = ''
    avatar_url: str = ''
    extra: dict = field(default_factory=dict)


# --- Google ---------------------------------------------------------------


def verify_google(credential: str) -> SocialProfile:
    """Verify a Google ID token (JWT) issued by Google Identity Services."""
    if not settings.GOOGLE_CLIENT_ID:
        raise ProviderNotConfigured('GOOGLE_CLIENT_ID is not set')
    try:
        info = google_id_token.verify_oauth2_token(
            credential, google_requests.Request(), settings.GOOGLE_CLIENT_ID
        )
    except ValueError as exc:
        raise ProviderError(f'Invalid Google token: {exc}') from exc

    if info.get('iss') not in ('accounts.google.com', 'https://accounts.google.com'):
        raise ProviderError('Invalid Google token issuer')

    return SocialProfile(
        provider='google',
        uid=info['sub'],
        email=info.get('email', ''),
        email_verified=bool(info.get('email_verified')),
        first_name=info.get('given_name', ''),
        last_name=info.get('family_name', ''),
        username_hint=(info.get('email') or '').split('@')[0],
        avatar_url=info.get('picture', ''),
        extra={k: info.get(k) for k in ('email', 'name', 'locale', 'hd') if info.get(k)},
    )


# --- Facebook -------------------------------------------------------------


def verify_facebook(access_token: str) -> SocialProfile:
    """Verify a Facebook user access token and fetch the profile."""
    app_id, app_secret = settings.FACEBOOK_APP_ID, settings.FACEBOOK_APP_SECRET
    if not app_id or not app_secret:
        raise ProviderNotConfigured('FACEBOOK_APP_ID / FACEBOOK_APP_SECRET are not set')

    graph = f'https://graph.facebook.com/{settings.FACEBOOK_GRAPH_VERSION}'

    # 1. Make sure the token is valid AND was issued for *our* app.
    try:
        debug = (
            requests.get(
                f'{graph}/debug_token',
                params={'input_token': access_token, 'access_token': f'{app_id}|{app_secret}'},
                timeout=HTTP_TIMEOUT,
            )
            .json()
            .get('data', {})
        )
    except (requests.RequestException, ValueError) as exc:
        raise ProviderError('Could not reach Facebook') from exc

    if not debug.get('is_valid') or str(debug.get('app_id')) != str(app_id):
        raise ProviderError('Invalid Facebook token')

    # 2. Fetch the profile. appsecret_proof binds the call to our app secret.
    proof = hmac.new(app_secret.encode(), access_token.encode(), hashlib.sha256).hexdigest()
    try:
        resp = requests.get(
            f'{graph}/me',
            params={
                'fields': 'id,first_name,last_name,email,picture.type(large)',
                'access_token': access_token,
                'appsecret_proof': proof,
            },
            timeout=HTTP_TIMEOUT,
        )
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise ProviderError('Could not reach Facebook') from exc

    if resp.status_code != 200 or 'id' not in data:
        raise ProviderError('Could not fetch Facebook profile')

    if data['id'] != str(debug.get('user_id')):
        raise ProviderError('Facebook token/user mismatch')

    email = data.get('email', '')
    return SocialProfile(
        provider='facebook',
        uid=data['id'],
        email=email,
        # Facebook only returns confirmed email addresses.
        email_verified=bool(email),
        first_name=data.get('first_name', ''),
        last_name=data.get('last_name', ''),
        username_hint=email.split('@')[0] if email else '',
        avatar_url=(data.get('picture') or {}).get('data', {}).get('url', ''),
    )


# --- Test mode ------------------------------------------------------------

MOCK_PROFILES = {
    # Google and Facebook share a verified email, so they merge into one user,
    # which demonstrates account linking. Telegram never provides an email.
    'google': dict(
        uid='mock-google-1',
        email='test.user@example.com',
        email_verified=True,
        first_name='Test',
        last_name='Google',
        username_hint='test_google',
    ),
    'facebook': dict(
        uid='mock-facebook-1',
        email='test.user@example.com',
        email_verified=True,
        first_name='Test',
        last_name='Facebook',
        username_hint='test_facebook',
    ),
    'telegram': dict(
        uid='mock-telegram-1',
        first_name='Test',
        last_name='Telegram',
        username_hint='test_telegram',
        extra={'username': 'test_telegram'},
    ),
}


def mock_profile(provider: str) -> SocialProfile:
    """Fake, unverified profile for local development (SOCIAL_AUTH_MOCK)."""
    if not (settings.DEBUG and settings.SOCIAL_AUTH_MOCK):
        raise ProviderError('Test mode is disabled')
    data = dict(MOCK_PROFILES[provider])
    data['extra'] = {**data.get('extra', {}), 'mock': True}
    return SocialProfile(provider=provider, **data)


# --- Telegram -------------------------------------------------------------

TELEGRAM_FIELDS = ('id', 'first_name', 'last_name', 'username', 'photo_url', 'auth_date')


def verify_telegram(payload: dict) -> SocialProfile:
    """
    Verify data from the Telegram Login Widget.
    https://core.telegram.org/widgets/login#checking-authorization
    """
    bot_token = settings.TELEGRAM_BOT_TOKEN
    if not bot_token:
        raise ProviderNotConfigured('TELEGRAM_BOT_TOKEN is not set')

    received_hash = str(payload.get('hash', ''))
    if not received_hash or 'id' not in payload or 'auth_date' not in payload:
        raise ProviderError('Incomplete Telegram data')

    data = {k: str(payload[k]) for k in TELEGRAM_FIELDS if payload.get(k) not in (None, '')}
    check_string = '\n'.join(f'{k}={data[k]}' for k in sorted(data))
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    expected_hash = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        raise ProviderError('Invalid Telegram signature')

    try:
        auth_date = int(data['auth_date'])
    except ValueError as exc:
        raise ProviderError('Invalid Telegram auth_date') from exc
    if time.time() - auth_date > settings.TELEGRAM_AUTH_MAX_AGE:
        raise ProviderError('Telegram authorization has expired')

    return SocialProfile(
        provider='telegram',
        uid=data['id'],
        first_name=data.get('first_name', ''),
        last_name=data.get('last_name', ''),
        username_hint=data.get('username', ''),
        avatar_url=data.get('photo_url', ''),
        extra={'username': data.get('username', '')},
    )
