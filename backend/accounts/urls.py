from django.urls import path

from .views import email, session, social, telegram

urlpatterns = [
    # Social sign-in
    path('providers/', social.ProvidersConfigView.as_view(), name='auth-providers'),
    path('google/', social.GoogleLoginView.as_view(), name='auth-google'),
    path('facebook/', social.FacebookLoginView.as_view(), name='auth-facebook'),
    path('telegram/', social.TelegramLoginView.as_view(), name='auth-telegram'),
    # Telegram bot code
    path('telegram/login/start/', telegram.TelegramLoginStartView.as_view(), name='telegram-start'),
    path(
        'telegram/login/status/', telegram.TelegramLoginStatusView.as_view(), name='telegram-status'
    ),
    path(
        'telegram/login/verify/', telegram.TelegramLoginVerifyView.as_view(), name='telegram-verify'
    ),
    path('telegram/webhook/', telegram.TelegramWebhookView.as_view(), name='telegram-webhook'),
    # Email + password
    path('login/', email.LoginView.as_view(), name='auth-login'),
    path('email/signup/', email.EmailSignUpView.as_view(), name='auth-email-signup'),
    path('email/verify/', email.EmailVerifyView.as_view(), name='auth-email-verify'),
    path('email/resend/', email.EmailResendView.as_view(), name='auth-email-resend'),
    path('password/reset/', email.PasswordResetRequestView.as_view(), name='password-reset'),
    path(
        'password/reset/verify/',
        email.PasswordResetVerifyView.as_view(),
        name='password-reset-verify',
    ),
    path(
        'password/reset/confirm/',
        email.PasswordResetConfirmView.as_view(),
        name='password-reset-confirm',
    ),
    # Session
    path('token/refresh/', session.CookieTokenRefreshView.as_view(), name='token-refresh'),
    path('logout/', session.LogoutView.as_view(), name='auth-logout'),
    path('me/', session.MeView.as_view(), name='auth-me'),
    path('social/<str:provider>/', session.DisconnectSocialView.as_view(), name='auth-disconnect'),
]
