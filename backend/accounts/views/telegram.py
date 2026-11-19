from django.conf import settings
from django.utils.crypto import constant_time_compare
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .. import providers, telegram_bot
from ..serializers import TelegramLoginTokenSerializer, TelegramLoginVerifySerializer
from ..throttles import TelegramLoginThrottle, TelegramVerifyThrottle
from .social import BaseSocialLoginView


def _error_response(exc):
    if isinstance(exc, telegram_bot.LoginExpired):
        return Response({'detail': str(exc), 'code': 'expired'}, status=status.HTTP_410_GONE)
    if isinstance(exc, (providers.ProviderNotConfigured, telegram_bot.TelegramError)):
        return Response({'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class TelegramLoginStartView(APIView):
    """-> {token, bot_link, bot_username, button_text, expires_in, code_length}."""

    permission_classes = (AllowAny,)
    authentication_classes = ()
    throttle_classes = (TelegramLoginThrottle,)

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        try:
            return Response(telegram_bot.start_login())
        except providers.ProviderError as exc:
            return _error_response(exc)


class TelegramLoginStatusView(APIView):
    """{token} -> {status: active}; polled while the page is open (410 once it expired)."""

    permission_classes = (AllowAny,)
    authentication_classes = ()
    throttle_classes = (TelegramLoginThrottle,)

    @extend_schema(request=TelegramLoginTokenSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = TelegramLoginTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            return Response(telegram_bot.login_status(serializer.validated_data['token']))
        except providers.ProviderError as exc:
            return _error_response(exc)


class TelegramLoginVerifyView(BaseSocialLoginView):
    """{token, code} -> signed in (or Telegram linked to the signed-in user)."""

    serializer_class = TelegramLoginVerifySerializer
    provider = 'telegram'
    throttle_classes = (TelegramVerifyThrottle,)

    @staticmethod
    def is_mock(request):
        return False  # test mode has its own endpoint (/telegram/)

    def verify(self, data):
        return telegram_bot.verify_login(data['token'], data['code'])


class TelegramWebhookView(APIView):
    """Production mode: Telegram pushes bot messages here (see `manage.py telegram_webhook`).

    Telegram sends the secret given to setWebhook in a header; anything else is rejected.
    """

    permission_classes = (AllowAny,)
    authentication_classes = ()
    throttle_classes = ()

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        secret = settings.TELEGRAM_WEBHOOK_SECRET
        given = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
        if not secret or not constant_time_compare(given, secret):
            return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            telegram_bot.handle_update(request.data)
        except telegram_bot.TelegramError:
            # Telegram retries non-2xx answers; a code we failed to send is better re-requested.
            pass
        return Response({'ok': True})
