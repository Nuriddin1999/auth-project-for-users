from django.urls import path

from . import views

urlpatterns = [
    path('providers/', views.ProvidersConfigView.as_view(), name='auth-providers'),
    path('google/', views.GoogleLoginView.as_view(), name='auth-google'),
    path('facebook/', views.FacebookLoginView.as_view(), name='auth-facebook'),
    path('telegram/', views.TelegramLoginView.as_view(), name='auth-telegram'),
    path('login/', views.LoginView.as_view(), name='auth-login'),
    path('email/signup/', views.EmailSignUpView.as_view(), name='auth-email-signup'),
    path('email/verify/', views.EmailVerifyView.as_view(), name='auth-email-verify'),
    path('email/resend/', views.EmailResendView.as_view(), name='auth-email-resend'),
    path('password/reset/', views.PasswordResetRequestView.as_view(), name='password-reset'),
    path(
        'password/reset/verify/',
        views.PasswordResetVerifyView.as_view(),
        name='password-reset-verify',
    ),
    path(
        'password/reset/confirm/',
        views.PasswordResetConfirmView.as_view(),
        name='password-reset-confirm',
    ),
    path('token/refresh/', views.CookieTokenRefreshView.as_view(), name='token-refresh'),
    path('logout/', views.LogoutView.as_view(), name='auth-logout'),
    path('me/', views.MeView.as_view(), name='auth-me'),
    path('social/<str:provider>/', views.DisconnectSocialView.as_view(), name='auth-disconnect'),
]
