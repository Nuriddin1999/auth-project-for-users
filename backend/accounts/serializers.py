from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import SocialAccount

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

    class Meta:
        model = User
        fields = (
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'avatar_url',
            'social_accounts',
            'date_joined',
        )
        read_only_fields = ('id', 'email', 'social_accounts', 'date_joined')

    def get_avatar_url(self, user):
        for account in user.social_accounts.all():
            if account.avatar_url:
                return account.avatar_url
        return ''
