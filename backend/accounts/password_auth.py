"""
Email + password sign in, and "forgot password" via an email code.

Reset flow:
  1. request_code(purpose=RESET)          -> code sent to the email
  2. verify_reset_code(email, code)       -> short-lived signed reset token
  3. reset_password(token, new_password)  -> password changed, user signed in

The reset token is signed with SECRET_KEY, expires after RESET_TOKEN_MAX_AGE and
contains a fingerprint of the current password hash, so it stops working as soon as
the password changes (one-time use).
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core import signing
from django.db import transaction
from django.utils.crypto import salted_hmac
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from .email_codes import EmailCodeError, consume_code, find_user_by_email, normalize_email
from .models import EmailCode

User = get_user_model()

RESET_TOKEN_SALT = 'accounts.password_reset'
RESET_TOKEN_MAX_AGE = 10 * 60  # seconds to choose the new password after the code

# Hashing a password is slow on purpose; doing it for unknown emails too keeps the
# response time the same, so timing doesn't reveal which emails have accounts.
_DUMMY_HASH = make_password('dummy-password-for-timing')


class InvalidCredentials(EmailCodeError):
    status = 401


def authenticate(email: str, password: str):
    """Return the user for a valid email + password, else raise InvalidCredentials."""
    user = find_user_by_email(normalize_email(email))
    if user is None:
        User(password=_DUMMY_HASH).check_password(password)
    elif user.has_usable_password() and user.check_password(password) and user.is_active:
        return user
    raise InvalidCredentials('Invalid email or password', code='invalid_credentials')


def _fingerprint(user) -> str:
    return salted_hmac(RESET_TOKEN_SALT, user.password).hexdigest()[:16]


def verify_reset_code(*, email: str, code: str) -> str:
    """Burn the reset code and return a token for setting the new password."""
    record = consume_code(purpose=EmailCode.Purpose.RESET, email=email, code=code)
    user = find_user_by_email(record.email)
    if user is None:
        raise EmailCodeError('Invalid or expired code', code='invalid_code')
    return signing.dumps({'uid': user.pk, 'fp': _fingerprint(user)}, salt=RESET_TOKEN_SALT)


def reset_password(*, token: str, password: str):
    """Set the new password if the token is valid; returns the user."""
    invalid = EmailCodeError(
        'This password reset link has expired. Please start again', code='invalid_token'
    )
    try:
        data = signing.loads(token, salt=RESET_TOKEN_SALT, max_age=RESET_TOKEN_MAX_AGE)
    except signing.BadSignature as exc:  # includes SignatureExpired
        raise invalid from exc

    user = User.objects.filter(pk=data.get('uid')).first()
    if user is None or data.get('fp') != _fingerprint(user):
        raise invalid  # unknown user, or the password was already changed with this token

    with transaction.atomic():
        user.set_password(password)
        user.save(update_fields=['password'])
        # Sign out every other session: all refresh tokens issued so far stop working.
        for outstanding in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=outstanding)
    return user
