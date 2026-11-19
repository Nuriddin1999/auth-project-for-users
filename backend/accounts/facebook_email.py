"""
Temporary stand-in for Facebook login while the Facebook app isn't set up
(FACEBOOK_EMAIL_FALLBACK=True and no FACEBOOK_APP_ID).

"Continue with Facebook" asks for an email instead of opening Facebook:
  1. {email}        -> a real 6-digit code is emailed
  2. {email, code}  -> the user with this email (created if needed) is signed in

It's an email-code sign-in, not a Facebook identity: no Facebook link is stored, so nothing
needs cleaning up once the real Facebook app is configured (this path then switches off).
"""

import secrets
import time

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils.crypto import constant_time_compare, salted_hmac

from .email_codes import _send_code_email
from .providers import ProviderError

CODE_LENGTH = 6
MAX_ATTEMPTS = 5


class CodeCooldown(ProviderError):
    def __init__(self, message, retry_after):
        super().__init__(message)
        self.retry_after = retry_after


def enabled() -> bool:
    return settings.FACEBOOK_EMAIL_FALLBACK and not settings.FACEBOOK_APP_ID


def _normalize(email: str) -> str:
    email = (email or '').strip().lower()
    try:
        validate_email(email)
    except ValidationError as exc:
        raise ProviderError('Enter a valid email address') from exc
    return email


def _key(email: str) -> str:
    return f'facebook-email:{email}'


def _hash(email: str, code: str) -> str:
    return salted_hmac('accounts.facebook_email', f'{email}:{code}').hexdigest()


def start(email: str) -> dict:
    """Step 1: email a code. Returns data for the code page."""
    email = _normalize(email)
    previous = cache.get(_key(email))
    now = time.time()
    if previous and previous['resend_at'] > now:
        wait = int(previous['resend_at'] - now) + 1
        raise CodeCooldown(f'Please wait {wait} s before requesting a new code', wait)

    code = f'{secrets.randbelow(10**CODE_LENGTH):0{CODE_LENGTH}d}'
    _send_code_email(email=email, code=code, purpose='facebook', name='')  # raises if not sent
    ttl = settings.EMAIL_CODE_TTL
    pending = {
        'code_hash': _hash(email, code),
        'attempts': 0,
        'expires_at': now + ttl,
        'resend_at': now + settings.EMAIL_CODE_RESEND_COOLDOWN,
    }
    cache.set(_key(email), pending, timeout=ttl)
    return {
        'detail': 'Code sent',
        'channel': 'email',
        'identity': email,
        'expires_in': ttl,
        'code_length': CODE_LENGTH,
    }


def verify(email: str, code: str) -> str:
    """Step 2: check the code; returns the (normalized) email it proves."""
    invalid = ProviderError('Invalid or expired code')
    email = _normalize(email)
    key = _key(email)
    pending = cache.get(key)
    remaining = pending['expires_at'] - time.time() if pending else 0
    if remaining <= 0:
        raise invalid

    if not constant_time_compare(pending['code_hash'], _hash(email, code.strip())):
        pending['attempts'] += 1
        if pending['attempts'] >= MAX_ATTEMPTS:
            cache.delete(key)  # too many guesses: start over
        else:
            cache.set(key, pending, timeout=remaining)
        raise invalid

    cache.delete(key)  # single use
    return email
