from django.contrib.auth.models import update_last_login
from rest_framework import status
from rest_framework.response import Response

from ..cookies import set_refresh_cookie
from ..serializers import UserSerializer
from ..services import issue_tokens


def login_response(user, created):
    """Common success response for every sign-in method: access token + refresh cookie."""
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


def cooldown_response(detail, retry_after):
    """429 with the seconds to wait, in the body (for the UI) and in Retry-After."""
    return Response(
        {'detail': detail, 'code': 'cooldown', 'retry_after': retry_after},
        status=status.HTTP_429_TOO_MANY_REQUESTS,
        headers={'Retry-After': str(retry_after)},
    )
