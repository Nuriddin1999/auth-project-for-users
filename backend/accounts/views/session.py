from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from ..cookies import clear_refresh_cookie, get_refresh_cookie, set_refresh_cookie
from ..models import SocialAccount
from ..serializers import UserSerializer


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = (IsAuthenticated,)
    http_method_names = ('get', 'patch')

    def get_object(self):
        return self.request.user


class DisconnectSocialView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    def delete(self, request, provider):
        user = request.user
        account = SocialAccount.objects.filter(user=user, provider=provider).first()
        if account is None:
            return Response({'detail': 'Not linked'}, status=status.HTTP_404_NOT_FOUND)
        others = SocialAccount.objects.filter(user=user).exclude(pk=account.pk).exists()
        # A stored email is always verified, so the user can still sign in with an email code.
        if not others and not user.email and not user.has_usable_password():
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

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
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

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
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
