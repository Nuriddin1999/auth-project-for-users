from django.contrib import admin

from .models import SocialAccount


@admin.register(SocialAccount)
class SocialAccountAdmin(admin.ModelAdmin):
    list_display = ('provider', 'uid', 'user', 'created_at', 'last_login_at')
    list_filter = ('provider',)
    search_fields = ('uid', 'user__username', 'user__email')
    raw_id_fields = ('user',)
