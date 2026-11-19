from django.conf import settings
from django.contrib.auth.models import update_last_login
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from . import providers
from .cookies import clear_refresh_cookie, get_refresh_cookie, set_refresh_cookie
from .models import SocialAccount
from .serializers import (
    FacebookLoginSerializer,
    GoogleLoginSerializer,
    TelegramLoginSerializer,
    UserSerializer,
)
from .services import AccountConflict, issue_tokens, resolve_user


class SocialLoginThrottle(AnonRateThrottle):
    rate = '30/min'


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

    def get_profile(self, request):
        if settings.SOCIAL_AUTH_MOCK and request.data.get('mock') is True:
            return providers.mock_profile(self.provider)
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.verify(serializer.validated_data)

    def post(self, request):
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

        if not user.is_active:
            return Response({'detail': 'User is disabled'}, status=status.HTTP_403_FORBIDDEN)

        update_last_login(None, user)
        tokens = issue_tokens(user)
        response = Response(
            {'access': tokens['access'], 'user': UserSerializer(user).data, 'created': created},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
        set_refresh_cookie(response, tokens['refresh'])
        return response


class GoogleLoginView(BaseSocialLoginView):
    serializer_class = GoogleLoginSerializer
    provider = 'google'

    def verify(self, data):
        return providers.verify_google(data['credential'])


class FacebookLoginView(BaseSocialLoginView):
    serializer_class = FacebookLoginSerializer
    provider = 'facebook'

    def verify(self, data):
        return providers.verify_facebook(data['access_token'])


class TelegramLoginView(BaseSocialLoginView):
    serializer_class = TelegramLoginSerializer
    provider = 'telegram'

    def verify(self, data):
        return providers.verify_telegram(data)


class ProvidersConfigView(APIView):
    """Public, non-secret config the frontend needs to render login buttons."""

    permission_classes = (AllowAny,)
    authentication_classes = ()

    def get(self, request):
        return Response(
            {
                'google': {'enabled': bool(settings.GOOGLE_CLIENT_ID)},
                'facebook': {
                    'enabled': bool(settings.FACEBOOK_APP_ID and settings.FACEBOOK_APP_SECRET)
                },
                'telegram': {'enabled': bool(settings.TELEGRAM_BOT_TOKEN)},
                'mock': settings.SOCIAL_AUTH_MOCK,
            }
        )


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = (IsAuthenticated,)
    http_method_names = ('get', 'patch')

    def get_object(self):
        return self.request.user


class DisconnectSocialView(APIView):
    permission_classes = (IsAuthenticated,)

    def delete(self, request, provider):
        user = request.user
        account = SocialAccount.objects.filter(user=user, provider=provider).first()
        if account is None:
            return Response({'detail': 'Not linked'}, status=status.HTTP_404_NOT_FOUND)
        others = SocialAccount.objects.filter(user=user).exclude(pk=account.pk).exists()
        if not others and not user.has_usable_password():
            return Response(
                {'detail': 'Cannot remove the only way to sign in'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        account.delete()
        return Response(UserSerializer(user).data)


class CookieTokenRefreshView(APIView):
    """Issue a new access token using the refresh token from the httpOnly cookie."""

    permission_classes = (AllowAny,)
    authentication_classes = ()

    def post(self, request):
        refresh = get_refresh_cookie(request)
        if not refresh:
            return Response({'detail': 'No refresh token'}, status=status.HTTP_401_UNAUTHORIZED)

        serializer = TokenRefreshSerializer(data={'refresh': refresh})
        try:
            serializer.is_valid(raise_exception=True)
        except (InvalidToken, TokenError):
            response = Response({'detail': 'Session expired'}, status=status.HTTP_401_UNAUTHORIZED)
            clear_refresh_cookie(response)
            return response

        data = serializer.validated_data
        response = Response({'access': data['access']})
        if 'refresh' in data:  # ROTATE_REFRESH_TOKENS: the old one is now blacklisted
            set_refresh_cookie(response, data['refresh'])
        return response


class LogoutView(APIView):
    """Blacklist the refresh token from the cookie and remove the cookie."""

    permission_classes = (AllowAny,)
    authentication_classes = ()

    def post(self, request):
        refresh = get_refresh_cookie(request)
        if refresh:
            try:
                RefreshToken(refresh).blacklist()
            except TokenError:
                pass  # already invalid/expired - the goal is achieved either way
        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_refresh_cookie(response)
        return response
