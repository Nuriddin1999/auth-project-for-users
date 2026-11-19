from django.contrib import admin

from .models import EmailCode, SocialAccount, TelegramChat


@admin.register(SocialAccount)
class SocialAccountAdmin(admin.ModelAdmin):
    list_display = ('provider', 'uid', 'user', 'created_at', 'last_login_at')
    list_filter = ('provider',)
    search_fields = ('uid', 'user__username', 'user__email')
    raw_id_fields = ('user',)


@admin.register(EmailCode)
class EmailCodeAdmin(admin.ModelAdmin):
    list_display = ('email', 'purpose', 'created_at', 'expires_at', 'used_at', 'attempts')
    list_filter = ('purpose',)
    search_fields = ('email',)
    readonly_fields = ('code_hash',)


@admin.register(TelegramChat)
class TelegramChatAdmin(admin.ModelAdmin):
    list_display = ('username', 'telegram_id', 'first_name', 'last_name', 'updated_at')
    search_fields = ('username', 'first_name', 'last_name')
