from django.urls import path

from . import views

urlpatterns = [
    path('providers/', views.ProvidersConfigView.as_view(), name='auth-providers'),
    path('google/', views.GoogleLoginView.as_view(), name='auth-google'),
    path('facebook/', views.FacebookLoginView.as_view(), name='auth-facebook'),
    path('telegram/', views.TelegramLoginView.as_view(), name='auth-telegram'),
    path('token/refresh/', views.CookieTokenRefreshView.as_view(), name='token-refresh'),
    path('logout/', views.LogoutView.as_view(), name='auth-logout'),
    path('me/', views.MeView.as_view(), name='auth-me'),
    path('social/<str:provider>/', views.DisconnectSocialView.as_view(), name='auth-disconnect'),
]
