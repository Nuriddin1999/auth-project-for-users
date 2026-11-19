"""Per-endpoint rate limits. Rates live in settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'].

Each group has its own scope so, for example, the Telegram page polling every 2 s
can't use up the budget for password sign-in.
"""

from rest_framework.throttling import AnonRateThrottle


class SocialLoginThrottle(AnonRateThrottle):
    scope = 'social_login'


class EmailCodeThrottle(AnonRateThrottle):
    scope = 'email_code'


class PasswordLoginThrottle(AnonRateThrottle):
    scope = 'password_login'


class TelegramLoginThrottle(AnonRateThrottle):
    scope = 'telegram_login'


class TelegramVerifyThrottle(AnonRateThrottle):
    scope = 'telegram_verify'  # codes are checked by value: keep guessing slow
