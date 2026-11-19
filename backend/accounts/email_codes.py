"""
One-time email codes: confirm the email on sign up, and confirm ownership
before resetting a forgotten password.

Protection against abuse:
- only an HMAC of the code is stored, the code itself is never saved;
- a code expires after EMAIL_CODE_TTL and works only once;
- each code allows EMAIL_CODE_MAX_ATTEMPTS wrong guesses, then it is burned;
- requesting a new code invalidates the previous one;
- resend cooldown and an hourly limit per email address.
"""

import logging
import secrets
import smtplib
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from .models import EmailCode
from .services import unique_username

User = get_user_model()
logger = logging.getLogger(__name__)


class EmailCodeError(Exception):
    status = 400

    def __init__(self, message, *, code='invalid', **extra):
        super().__init__(message)
        self.code = code
        self.extra = extra


class AccountExists(EmailCodeError):
    status = 409


class AccountNotFound(EmailCodeError):
    status = 404


class TooManyRequests(EmailCodeError):
    status = 429


class EmailNotSent(EmailCodeError):
    status = 503


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _hash(email: str, code: str) -> str:
    # Bound to the email, so a code hash can't be reused for another address.
    return salted_hmac('accounts.email_code', f'{email}:{code}').hexdigest()


def find_user_by_email(email: str):
    return User.objects.filter(email__iexact=email).first()


def _check_rate_limits(email: str, purpose: str):
    now = timezone.now()
    recent = EmailCode.objects.filter(email=email, created_at__gte=now - timedelta(hours=1))

    # Cooldown applies to re-sending while a code for the same purpose is still
    # pending - not to e.g. signing in right after the sign-up code was used.
    last = recent.filter(purpose=purpose, used_at__isnull=True).first()
    if last:
        wait = settings.EMAIL_CODE_RESEND_COOLDOWN - (now - last.created_at).total_seconds()
        if wait > 0:
            raise TooManyRequests(
                f'Please wait {int(wait) + 1} s before requesting a new code',
                code='cooldown',
                retry_after=int(wait) + 1,
            )
    if recent.count() >= settings.EMAIL_CODE_MAX_PER_HOUR:
        raise TooManyRequests('Too many codes requested, try again later', code='hourly_limit')


def test_code() -> str | None:
    """Fixed development code (EMAIL_TEST_CODE), only ever active with DEBUG."""
    code = settings.EMAIL_TEST_CODE
    return code if settings.DEBUG and code.isdigit() else None


def request_code(
    *, purpose: str, email: str, name: str = '', password: str = '', password_hash: str = ''
) -> dict:
    """Send a code; returns {expires_in, code_length} for the verification page.

    On sign up the chosen password is kept (hashed) with the pending code and is
    applied to the account only after the email is confirmed.
    """
    email = normalize_email(email)
    user = find_user_by_email(email)

    if purpose == EmailCode.Purpose.SIGNUP and user:
        raise AccountExists('An account with this email already exists', code='account_exists')
    if purpose == EmailCode.Purpose.RESET and not user:
        raise AccountNotFound('No account with this email', code='account_not_found')

    _check_rate_limits(email, purpose)

    code = test_code()
    if code:
        logger.warning('EMAIL_TEST_CODE is active: no email sent to %s, code: %s', email, code)
    else:
        length = settings.EMAIL_CODE_LENGTH
        code = f'{secrets.randbelow(10**length):0{length}d}'
        # Send first, save after: if the email can't be delivered, nothing is stored,
        # the previous code keeps working and the attempt doesn't eat the rate limit.
        _send_code_email(email=email, code=code, purpose=purpose, name=name.strip())

    now = timezone.now()
    with transaction.atomic():
        EmailCode.objects.filter(email=email, used_at__isnull=True).update(used_at=now)
        EmailCode.objects.create(
            email=email,
            purpose=purpose,
            name=name.strip(),
            password_hash=make_password(password) if password else password_hash,
            code_hash=_hash(email, code),
            expires_at=now + timedelta(seconds=settings.EMAIL_CODE_TTL),
        )
    return {'expires_in': settings.EMAIL_CODE_TTL, 'code_length': len(code)}


def _send_code_email(*, email: str, code: str, purpose: str, name: str) -> None:
    context = {
        'code': code,
        'name': name,
        'is_signup': purpose == EmailCode.Purpose.SIGNUP,
        'is_reset': purpose == EmailCode.Purpose.RESET,
        'minutes': settings.EMAIL_CODE_TTL // 60,
    }
    try:
        send_mail(
            subject=f'{code} is your verification code',
            message=render_to_string('accounts/email_code.txt', context),
            html_message=render_to_string('accounts/email_code.html', context),
            from_email=None,
            recipient_list=[email],
        )
    except (smtplib.SMTPException, OSError) as exc:  # OSError: DNS, refused, timeout
        logger.exception('Could not send verification code to %s', email)
        raise EmailNotSent(
            'Could not send the email. Please try again later', code='email_failed'
        ) from exc


def resend_code(*, purpose: str, email: str) -> dict:
    """Send a new code, reusing the name and password from the pending sign up.

    The frontend never has to keep the password around to resend a sign-up code.
    """
    email = normalize_email(email)
    last = EmailCode.objects.filter(email=email, purpose=purpose).first()
    if purpose == EmailCode.Purpose.SIGNUP and last is None:
        raise EmailCodeError('Please start the sign up again', code='signup_required')
    return request_code(
        purpose=purpose,
        email=email,
        name=last.name if last else '',
        password_hash=last.password_hash if last else '',
    )


def consume_code(*, purpose: str, email: str, code: str) -> EmailCode:
    """Check and burn the latest code; raises EmailCodeError if it doesn't match."""
    email = normalize_email(email)
    invalid = EmailCodeError('Invalid or expired code', code='invalid_code')

    # The error is raised only AFTER the transaction commits, so the
    # wrong-attempt counter is saved instead of being rolled back.
    error = None
    with transaction.atomic():
        record = (
            EmailCode.objects.select_for_update()
            .filter(email=email, purpose=purpose, used_at__isnull=True)
            .first()
        )
        now = timezone.now()
        if record is None or record.expires_at < now:
            error = invalid
        elif not constant_time_compare(record.code_hash, _hash(email, code.strip())):
            record.attempts += 1
            if record.attempts >= settings.EMAIL_CODE_MAX_ATTEMPTS:
                record.used_at = now  # too many guesses: burn the code
            record.save(update_fields=['attempts', 'used_at'])
            error = invalid
        else:
            record.used_at = now
            record.save(update_fields=['used_at'])

    if error:
        raise error
    return record


def verify_signup(*, email: str, code: str):
    """Confirm the sign-up code and create the account. Returns (user, created)."""
    record = consume_code(purpose=EmailCode.Purpose.SIGNUP, email=email, code=code)
    user = find_user_by_email(record.email)
    if user:
        # The email got an account meanwhile (e.g. via Google). Ownership is proven by
        # the code, so sign in - and give a passwordless account the chosen password.
        if not user.has_usable_password() and record.password_hash:
            user.password = record.password_hash
            user.save(update_fields=['password'])
        return user, False
    return _create_user(record.email, record.name, record.password_hash), True


def _create_user(email: str, name: str, password_hash: str):
    first_name, _, last_name = name.partition(' ')
    user = User(
        username=unique_username(email.split('@')[0], 'email', email),
        email=email,
        first_name=first_name[:150],
        last_name=last_name.strip()[:150],
    )
    if password_hash:
        user.password = password_hash
    else:
        user.set_unusable_password()
    try:
        with transaction.atomic():
            user.save()
    except IntegrityError as exc:  # a concurrent request created it first
        raise EmailCodeError('Please try again', code='retry') from exc
    return user
