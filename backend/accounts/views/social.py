from django.conf import settings
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .. import email_codes, facebook_email, mock_social, providers
from ..serializers import (
    FacebookLoginSerializer,
    GoogleLoginSerializer,
    MockSocialSerializer,
    TelegramLoginSerializer,
)
from ..services import AccountConflict, get_or_create_email_user, resolve_user
from ..throttles import SocialLoginThrottle
from .common import cooldown_response, login_response


class BaseSocialLoginView(APIView):
    """
    POST provider credentials -> verify -> {access, user, created}
    plus the refresh token in an httpOnly cookie.

    If the request carries a valid access token, the provider account is
    linked to the current user instead of logging in as someone else.
    """

    permission_classes = (AllowAny,)
    throttle_classes = (SocialLoginThrottle,)
    serializer_class = None
    provider = None

    def verify(self, data):
        raise NotImplementedError

    @staticmethod
    def is_mock(request):
        return settings.SOCIAL_AUTH_MOCK and request.data.get('mock') is True

    def get_profile(self, request):
        if self.is_mock(request):
            # Test mode, step 2: identity + code -> profile.
            data = MockSocialSerializer(data=request.data)
            data.is_valid(raise_exception=True)
            return mock_social.verify(self.provider, **data.validated_data)
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.verify(serializer.validated_data)

    def post(self, request):
        if self.is_mock(request) and 'code' not in request.data:
            return self.mock_start(request)
        try:
            profile = self.get_profile(request)
            current = request.user if request.user.is_authenticated else None
            user, created = resolve_user(profile, current_user=current)
        except providers.ProviderNotConfigured as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except AccountConflict as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_409_CONFLICT)
        except providers.ProviderError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_401_UNAUTHORIZED)

        return login_response(user, created)

    def mock_start(self, request):
        """Test mode, step 1: {mock, identity} -> pretend a code was sent."""
        identity = str(request.data.get('identity', ''))
        try:
            return Response(mock_social.start(self.provider, identity))
        except providers.ProviderError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class GoogleLoginView(BaseSocialLoginView):
    serializer_class = GoogleLoginSerializer
    provider = 'google'

    def verify(self, data):
        return providers.verify_google(data['credential'])


class FacebookLoginView(BaseSocialLoginView):
    """Facebook access token -> session.

    Until the Facebook app is set up (FACEBOOK_EMAIL_FALLBACK): {email} -> a code is
    emailed, {email, code} -> signed in by that email (see facebook_email.py).
    """

    serializer_class = FacebookLoginSerializer
    provider = 'facebook'

    def verify(self, data):
        return providers.verify_facebook(data['access_token'])

    def post(self, request):
        if facebook_email.enabled() and 'email' in request.data:
            return self.email_fallback(request)
        return super().post(request)

    def email_fallback(self, request):
        if request.user.is_authenticated:
            return Response(
                {'detail': "Facebook isn't set up yet, so it can't be connected"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        email = str(request.data['email'])
        if 'code' not in request.data:
            try:
                return Response(facebook_email.start(email))
            except facebook_email.CodeCooldown as exc:
                return cooldown_response(str(exc), exc.retry_after)
            except providers.ProviderError as exc:
                return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            except email_codes.EmailNotSent as exc:
                return Response({'detail': str(exc)}, status=exc.status)

        try:
            proven = facebook_email.verify(email, str(request.data['code'])[:16])
        except providers.ProviderError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_401_UNAUTHORIZED)
        user, created = get_or_create_email_user(proven)
        return login_response(user, created)


class TelegramLoginView(BaseSocialLoginView):
    """Telegram Login Widget data (HMAC-signed) -> session. Alternative to the bot code flow."""

    serializer_class = TelegramLoginSerializer
    provider = 'telegram'

    def verify(self, data):
        return providers.verify_telegram(data)


class ProvidersConfigView(APIView):
    """Public, non-secret config the frontend needs to render login buttons."""

    permission_classes = (AllowAny,)
    authentication_classes = ()

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(
            {
                'google': {'enabled': bool(settings.GOOGLE_CLIENT_ID)},
                'facebook': {
                    'enabled': bool(settings.FACEBOOK_APP_ID and settings.FACEBOOK_APP_SECRET),
                    'email_fallback': facebook_email.enabled(),
                },
                'telegram': {'enabled': bool(settings.TELEGRAM_BOT_TOKEN)},
                'mock': settings.SOCIAL_AUTH_MOCK,
            }
        )
