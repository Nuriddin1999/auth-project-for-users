"""
Test mode for social login (SOCIAL_AUTH_MOCK, DEBUG only).

Simulates a provider sign-in without real keys, in two steps:
  1. {mock: true, identity}        -> "code sent" (Google/Facebook: email, Telegram: @username)
  2. {mock: true, identity, code}  -> verified SocialProfile -> normal login

Nothing is really sent: the code is always SOCIAL_AUTH_MOCK_CODE (12345 by default).
Pending verifications live in the cache with a TTL and a wrong-attempt limit.
"""

import re
import time

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from .providers import ProviderError, SocialProfile

MAX_ATTEMPTS = 5
TELEGRAM_USERNAME = re.compile(r'^[A-Za-z][A-Za-z0-9_]{4,31}$')

CHANNELS = {'google': 'email', 'facebook': 'email', 'telegram': 'telegram'}


def _ensure_enabled():
    if not (settings.DEBUG and settings.SOCIAL_AUTH_MOCK):
        raise ProviderError('Test mode is disabled')


def normalize_identity(provider: str, identity: str) -> str:
    identity = (identity or '').strip()
    if CHANNELS[provider] == 'email':
        identity = identity.lower()
        try:
            validate_email(identity)
        except ValidationError as exc:
            raise ProviderError('Enter a valid email address') from exc
        return identity

    identity = identity.removeprefix('@')
    if not TELEGRAM_USERNAME.match(identity):
        raise ProviderError(
            'Enter a valid Telegram username: 5-32 letters, digits or _, starting with a letter'
        )
    return identity.lower()


def _key(provider: str, identity: str) -> str:
    return f'mock-social:{provider}:{identity}'


def start(provider: str, identity: str) -> dict:
    """Step 1: pretend to send a code. Returns data for the code page."""
    _ensure_enabled()
    identity = normalize_identity(provider, identity)
    ttl = settings.EMAIL_CODE_TTL
    pending = {'attempts': 0, 'expires_at': time.time() + ttl}
    cache.set(_key(provider, identity), pending, timeout=ttl)
    return {
        'detail': 'Code sent',
        'channel': CHANNELS[provider],
        'identity': identity,
        'expires_in': settings.EMAIL_CODE_TTL,
        'code_length': len(settings.SOCIAL_AUTH_MOCK_CODE),
    }


def verify(provider: str, identity: str, code: str) -> SocialProfile:
    """Step 2: check the code and return the (fake) provider profile."""
    _ensure_enabled()
    identity = normalize_identity(provider, identity)
    key = _key(provider, identity)
    pending = cache.get(key)
    remaining = pending['expires_at'] - time.time() if pending else 0
    if remaining <= 0:
        raise ProviderError('Invalid or expired code')

    if code.strip() != settings.SOCIAL_AUTH_MOCK_CODE:
        pending['attempts'] += 1
        if pending['attempts'] >= MAX_ATTEMPTS:
            cache.delete(key)  # too many guesses: start over
        else:
            cache.set(key, pending, timeout=remaining)  # keep the original expiry
        raise ProviderError('Invalid or expired code')

    cache.delete(key)
    return _profile(provider, identity)


def _profile(provider: str, identity: str) -> SocialProfile:
    if provider == 'telegram':
        return SocialProfile(
            provider=provider,
            uid=f'mock:{identity}',
            first_name=identity,
            username_hint=identity,
            extra={'username': identity, 'mock': True},
        )
    local = identity.split('@')[0]
    return SocialProfile(
        provider=provider,
        uid=f'mock:{identity}',
        email=identity,
        email_verified=True,  # "confirmed" with the code
        first_name=local.replace('.', ' ').replace('_', ' ').title()[:150],
        username_hint=local,
        extra={'mock': True},
    )
