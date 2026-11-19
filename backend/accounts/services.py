from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils.text import slugify
from rest_framework_simplejwt.tokens import RefreshToken

from .models import SocialAccount
from .providers import ProviderError, SocialProfile

User = get_user_model()


class AccountConflict(ProviderError):
    pass


def unique_username(hint: str, provider: str, uid: str) -> str:
    base = slugify(hint)[:120] or f'{provider}_{uid}'[:120]
    username, n = base, 1
    while User.objects.filter(username=username).exists():
        n += 1
        username = f'{base}_{n}'
    return username


@transaction.atomic
def resolve_user(profile: SocialProfile, current_user=None):
    """
    Find or create the user for a verified provider profile.

    - Already linked identity -> that user.
    - `current_user` given (logged-in user connecting another provider) -> link to them.
    - Verified email matching an existing user -> link to that user.
    - Otherwise -> create a new user.
    Returns (user, created).
    """
    account = (
        SocialAccount.objects.select_related('user')
        .filter(provider=profile.provider, uid=profile.uid)
        .first()
    )

    if account:
        if current_user is not None and account.user_id != current_user.pk:
            raise AccountConflict(f'This {profile.provider} account is linked to another user')
        _update_account(account, profile)
        return account.user, False

    created = False
    user = current_user
    if user is None and profile.email and profile.email_verified:
        user = User.objects.filter(email__iexact=profile.email).first()

    if user is None:
        user = User(
            username=unique_username(profile.username_hint, profile.provider, profile.uid),
            email=profile.email if profile.email_verified else '',
            first_name=profile.first_name[:150],
            last_name=profile.last_name[:150],
        )
        user.set_unusable_password()
        user.save()
        created = True
    elif (
        user.pk
        and current_user is not None
        and SocialAccount.objects.filter(user=user, provider=profile.provider).exists()
    ):
        raise AccountConflict(f'You already have a {profile.provider} account linked')

    try:
        account = SocialAccount.objects.create(
            user=user,
            provider=profile.provider,
            uid=profile.uid,
            avatar_url=profile.avatar_url[:1000],
            extra_data=profile.extra,
        )
    except IntegrityError as exc:  # concurrent request linked it first
        raise AccountConflict('This account was just linked, please retry') from exc

    return user, created


def _update_account(account: SocialAccount, profile: SocialProfile):
    account.avatar_url = profile.avatar_url[:1000]
    account.extra_data = profile.extra
    account.save(update_fields=['avatar_url', 'extra_data', 'last_login_at'])


def issue_tokens(user) -> dict:
    refresh = RefreshToken.for_user(user)
    return {'access': str(refresh.access_token), 'refresh': str(refresh)}
