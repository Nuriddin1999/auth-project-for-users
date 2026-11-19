from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .. import email_codes, password_auth
from ..models import EmailCode
from ..serializers import (
    EmailResendSerializer,
    EmailSignUpSerializer,
    EmailVerifySerializer,
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
)
from ..throttles import EmailCodeThrottle, PasswordLoginThrottle
from .common import login_response


class EmailCodeBaseView(APIView):
    permission_classes = (AllowAny,)
    authentication_classes = ()
    throttle_classes = (EmailCodeThrottle,)

    @staticmethod
    def error_response(exc):
        response = Response({'detail': str(exc), 'code': exc.code, **exc.extra}, status=exc.status)
        if 'retry_after' in exc.extra:
            response['Retry-After'] = str(exc.extra['retry_after'])
        return response


class EmailSignUpView(EmailCodeBaseView):
    """Sign up, step 1: {name, email, password, password_confirm} -> code sent to the email."""

    @extend_schema(request=EmailSignUpSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = EmailSignUpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            sent = email_codes.request_code(
                purpose=EmailCode.Purpose.SIGNUP, **serializer.validated_data
            )
        except email_codes.EmailCodeError as exc:
            return self.error_response(exc)
        return Response({'detail': 'Code sent', **sent})


class EmailVerifyView(EmailCodeBaseView):
    """Sign up, step 2: {email, code} -> account created.

    Deliberately does NOT sign the user in: after registration they sign in with
    their email and password (no tokens, no refresh cookie here).
    """

    @extend_schema(request=EmailVerifySerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = EmailVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user, created = email_codes.verify_signup(**serializer.validated_data)
        except email_codes.EmailCodeError as exc:
            return self.error_response(exc)
        return Response(
            {'detail': 'Account created', 'email': user.email, 'created': created},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class EmailResendView(EmailCodeBaseView):
    """{email, purpose} -> a new code for a pending sign up or password reset."""

    @extend_schema(request=EmailResendSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = EmailResendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            sent = email_codes.resend_code(**serializer.validated_data)
        except email_codes.EmailCodeError as exc:
            return self.error_response(exc)
        return Response({'detail': 'Code sent', **sent})


class LoginView(EmailCodeBaseView):
    """{email, password} -> {access, user, created} + refresh cookie."""

    throttle_classes = (PasswordLoginThrottle,)

    @extend_schema(request=LoginSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = password_auth.authenticate(**serializer.validated_data)
        except email_codes.EmailCodeError as exc:
            return self.error_response(exc)
        return login_response(user, created=False)


class PasswordResetRequestView(EmailCodeBaseView):
    """Forgot password, step 1: {email} -> code sent to the email."""

    @extend_schema(request=PasswordResetRequestSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            sent = email_codes.request_code(
                purpose=EmailCode.Purpose.RESET, **serializer.validated_data
            )
        except email_codes.EmailCodeError as exc:
            return self.error_response(exc)
        return Response({'detail': 'Code sent', **sent})


class PasswordResetVerifyView(EmailCodeBaseView):
    """Forgot password, step 2: {email, code} -> {reset_token}."""

    @extend_schema(request=EmailVerifySerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = EmailVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            token = password_auth.verify_reset_code(**serializer.validated_data)
        except email_codes.EmailCodeError as exc:
            return self.error_response(exc)
        return Response({'reset_token': token})


class PasswordResetConfirmView(EmailCodeBaseView):
    """Forgot password, step 3: {token, password, password_confirm} -> signed in."""

    @extend_schema(request=PasswordResetConfirmSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = password_auth.reset_password(**serializer.validated_data)
        except email_codes.EmailCodeError as exc:
            return self.error_response(exc)
        return login_response(user, created=False)
