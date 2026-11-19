from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import EmailCode, SocialAccount

User = get_user_model()


class GoogleLoginSerializer(serializers.Serializer):
    credential = serializers.CharField(help_text='Google ID token (JWT)')


class FacebookLoginSerializer(serializers.Serializer):
    access_token = serializers.CharField()


class TelegramLoginSerializer(serializers.Serializer):
    # trim_whitespace=False: values must stay byte-identical for the hash check.
    id = serializers.IntegerField()
    first_name = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)
    last_name = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)
    username = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)
    photo_url = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)
    auth_date = serializers.IntegerField()
    hash = serializers.CharField()


class SocialAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = SocialAccount
        fields = ('provider', 'uid', 'avatar_url', 'created_at')


class UserSerializer(serializers.ModelSerializer):
    social_accounts = SocialAccountSerializer(many=True, read_only=True)
    avatar_url = serializers.SerializerMethodField()
    has_password = serializers.BooleanField(source='has_usable_password', read_only=True)

    class Meta:
        model = User
        fields = (
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'avatar_url',
            'has_password',
            'social_accounts',
            'date_joined',
        )
        read_only_fields = ('id', 'email', 'social_accounts', 'date_joined')

    def get_avatar_url(self, user) -> str:
        for account in user.social_accounts.all():
            if account.avatar_url:
                return account.avatar_url
        return ''


def _check_passwords(attrs, user=None):
    """password == password_confirm, and passes Django's password validators."""
    if attrs['password'] != attrs.pop('password_confirm'):
        raise serializers.ValidationError({'password_confirm': ['Passwords do not match']})
    try:
        validate_password(attrs['password'], user=user)
    except DjangoValidationError as exc:
        raise serializers.ValidationError({'password': list(exc.messages)}) from exc
    return attrs


class EmailSignUpSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(max_length=128, trim_whitespace=False)
    password_confirm = serializers.CharField(max_length=128, trim_whitespace=False)

    def validate(self, attrs):
        # A throwaway user lets the validators reject passwords similar to name/email.
        return _check_passwords(attrs, User(email=attrs['email'], first_name=attrs['name']))


class EmailVerifySerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    # 6 digits normally; the development EMAIL_TEST_CODE may have another length.
    code = serializers.RegexField(
        r'^\s*\d{4,8}\s*$', error_messages={'invalid': 'Enter the code from the email'}
    )


class EmailResendSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    purpose = serializers.ChoiceField(choices=EmailCode.Purpose.choices)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(max_length=128, trim_whitespace=False)


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)


class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=500)
    password = serializers.CharField(max_length=128, trim_whitespace=False)
    password_confirm = serializers.CharField(max_length=128, trim_whitespace=False)

    def validate(self, attrs):
        return _check_passwords(attrs)


class MockSocialSerializer(serializers.Serializer):
    """Test mode social login: email (Google/Facebook) or Telegram username + code."""

    identity = serializers.CharField(max_length=254)
    code = serializers.CharField(max_length=8)


class TelegramLoginTokenSerializer(serializers.Serializer):
    token = serializers.RegexField(r'^[A-Za-z0-9_-]{16,64}$')


class TelegramLoginVerifySerializer(TelegramLoginTokenSerializer):
    code = serializers.RegexField(
        r'^\s*\d{6}\s*$', error_messages={'invalid': 'Enter the 6-digit code'}
    )
