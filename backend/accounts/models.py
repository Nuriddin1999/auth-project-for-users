from django.conf import settings
from django.db import models


class SocialAccount(models.Model):
    """Links a Django user to an identity at an external provider."""

    class Provider(models.TextChoices):
        GOOGLE = 'google', 'Google'
        FACEBOOK = 'facebook', 'Facebook'
        TELEGRAM = 'telegram', 'Telegram'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='social_accounts'
    )
    provider = models.CharField(max_length=20, choices=Provider.choices)
    uid = models.CharField(max_length=255, help_text='User id at the provider')
    avatar_url = models.URLField(max_length=1000, blank=True)
    extra_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_login_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['provider', 'uid'], name='unique_provider_uid'),
        ]

    def __str__(self):
        return f'{self.provider}:{self.uid} -> {self.user}'


class EmailCode(models.Model):
    """One-time code sent by email: confirm sign up or a password reset."""

    class Purpose(models.TextChoices):
        SIGNUP = 'signup', 'Sign up'
        RESET = 'reset', 'Password reset'

    email = models.EmailField(db_index=True)
    purpose = models.CharField(max_length=10, choices=Purpose.choices)
    code_hash = models.CharField(max_length=128, help_text='HMAC of the code, never the code')
    name = models.CharField(max_length=150, blank=True, help_text='Full name entered on sign up')
    password_hash = models.CharField(
        max_length=128, blank=True, help_text='Hashed password chosen on sign up'
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f'{self.purpose} code for {self.email}'
