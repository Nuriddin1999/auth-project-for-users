"""
The refresh token lives only in an httpOnly cookie, so JavaScript (and any XSS)
can never read it. The short-lived access token is returned in the JSON body and
kept in memory by the frontend.

SameSite=Lax prevents the browser from sending the cookie on cross-site POSTs,
which protects the cookie-based endpoints (refresh/logout) against CSRF.
"""

from django.conf import settings


def set_refresh_cookie(response, refresh_token: str) -> None:
    response.set_cookie(
        settings.AUTH_REFRESH_COOKIE_NAME,
        refresh_token,
        max_age=int(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds()),
        httponly=True,
        secure=settings.AUTH_REFRESH_COOKIE_SECURE,
        samesite=settings.AUTH_REFRESH_COOKIE_SAMESITE,
        path=settings.AUTH_REFRESH_COOKIE_PATH,
    )


def clear_refresh_cookie(response) -> None:
    response.delete_cookie(
        settings.AUTH_REFRESH_COOKIE_NAME,
        path=settings.AUTH_REFRESH_COOKIE_PATH,
        samesite=settings.AUTH_REFRESH_COOKIE_SAMESITE,
    )


def get_refresh_cookie(request) -> str | None:
    return request.COOKIES.get(settings.AUTH_REFRESH_COOKIE_NAME)
