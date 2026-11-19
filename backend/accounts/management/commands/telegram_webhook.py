from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounts import telegram_bot


class Command(BaseCommand):
    help = (
        'Production: register the bot webhook (Telegram pushes messages to the site). '
        '--delete switches back to getUpdates polling for local development.'
    )

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            '--url', help='Public HTTPS URL, e.g. https://example.com/api/auth/telegram/webhook/'
        )
        group.add_argument('--delete', action='store_true', help='Remove the webhook')

    def handle(self, *args, url=None, delete=False, **options):
        try:
            if delete:
                telegram_bot.delete_webhook()
                self.stdout.write(self.style.SUCCESS('Webhook removed: back to polling.'))
                self.stdout.write('Also unset TELEGRAM_WEBHOOK_SECRET and restart the server.')
                return
            if not settings.TELEGRAM_WEBHOOK_SECRET:
                raise CommandError('Set TELEGRAM_WEBHOOK_SECRET first (any long random string).')
            if not url.startswith('https://'):
                raise CommandError('Telegram only delivers webhooks to HTTPS URLs.')
            telegram_bot.set_webhook(url)
        except telegram_bot.TelegramError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f'Webhook set: {url}'))
