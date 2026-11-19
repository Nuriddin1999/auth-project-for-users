"""
Sign in with Telegram: get a code from our bot -> enter it on the site.

  1. start_login(): a short-lived sign-in page session (token) + a link to the bot.
  2. In the bot the user presses the "🔑 Get sign-in code" button (a reply-keyboard button:
     it sends plain text, no /start). Only the very first time Telegram itself requires
     Start; the bot answers it with a code too and shows the button for next time.
  3. The bot sends a 6-digit code to that Telegram account.
  4. verify_login(token, code): the code typed on the website -> the Telegram profile.

Two ways to receive bot messages:
  - development (default): while a sign-in page is open it polls login_status(), which pulls
    new messages with getUpdates - works on localhost, no public URL needed. A cache lock
    keeps parallel polls from handling the same message twice.
  - production (TELEGRAM_WEBHOOK_SECRET set): Telegram pushes each message to the webhook
    view (`manage.py telegram_webhook --url ...` registers it); polling is switched off.

A code proves the Telegram account it was sent to. Codes are HMAC-stored, single-use and
live EMAIL_CODE_TTL; a new code replaces the previous one. Guessing is limited per page
session (5 attempts), per IP (throttle) and by the short lifetime.
"""

import logging
import secrets
import time

import requests
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils.crypto import salted_hmac

from .models import TelegramChat
from .providers import ProviderError, ProviderNotConfigured, SocialProfile

logger = logging.getLogger(__name__)

API = 'https://api.telegram.org/bot{token}/{method}'
HTTP_TIMEOUT = 10
OFFSET_KEY = 'telegram:updates-offset'
SYNC_LOCK_KEY = 'telegram:sync-lock'
CODE_LENGTH = 6
MAX_ATTEMPTS = 5
LOGIN_TTL = 10 * 60  # how long a sign-in page stays usable
CODE_BUTTON = '🔑 Get sign-in code'
# Persistent button under the message box: one tap sends CODE_BUTTON as plain text.
KEYBOARD = {'keyboard': [[{'text': CODE_BUTTON}]], 'resize_keyboard': True, 'is_persistent': True}


class TelegramError(ProviderError):
    """Telegram API is unreachable or rejected the call."""


class LoginExpired(ProviderError):
    pass


# --- Bot API ----------------------------------------------------------------


def _api(method: str, **params):
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        raise ProviderNotConfigured('TELEGRAM_BOT_TOKEN is not set')
    try:
        resp = requests.post(
            API.format(token=token, method=method), json=params, timeout=HTTP_TIMEOUT
        )
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise TelegramError('Could not reach Telegram, please try again') from exc
    if not data.get('ok'):
        logger.warning('Telegram %s failed: %s', method, data.get('description'))
        raise TelegramError('Telegram rejected the request, please try again')
    return data['result']


def set_webhook(url: str) -> None:
    """Production: make Telegram push messages to `url` (signed with TELEGRAM_WEBHOOK_SECRET)."""
    _api(
        'setWebhook',
        url=url,
        secret_token=settings.TELEGRAM_WEBHOOK_SECRET,
        allowed_updates=['message'],
    )


def delete_webhook() -> None:
    """Back to getUpdates polling (development)."""
    _api('deleteWebhook')


def bot_username() -> str:
    name = cache.get('telegram:bot-username')
    if not name:
        name = _api('getMe')['username']
        cache.set('telegram:bot-username', name, timeout=3600)
    return name


def _send_quietly(chat_id: int, text: str, **params) -> None:
    try:
        _api('sendMessage', chat_id=chat_id, text=text, **params)
    except TelegramError:
        pass  # informational replies are a courtesy


# --- Sign-in page session (in the cache, keyed by a one-time token) ---------


def _login_key(token: str) -> str:
    return f'telegram:login:{token}'


def _load(token: str) -> dict:
    pending = cache.get(_login_key(token))
    if not pending or pending['expires_at'] <= time.time():
        raise LoginExpired('This sign-in page has expired. Please try again')
    return pending


def start_login() -> dict:
    """Create a sign-in page session and the link that opens the bot."""
    token = secrets.token_urlsafe(24)
    cache.set(_login_key(token), {'attempts': 0, 'expires_at': time.time() + LOGIN_TTL}, LOGIN_TTL)
    bot = bot_username()
    return {
        'token': token,
        'bot_username': bot,
        'bot_link': f'https://t.me/{bot}',
        'button_text': CODE_BUTTON,
        'expires_in': LOGIN_TTL,
        'code_length': CODE_LENGTH,
    }


def login_status(token: str) -> dict:
    """Polled while the sign-in page is open: processes new bot messages."""
    pending = _load(token)  # fail fast on unknown / expired sessions
    if not settings.TELEGRAM_WEBHOOK_SECRET:
        sync_updates()  # webhook mode: Telegram delivers messages by itself
    return {'status': 'active', 'expires_in': int(pending['expires_at'] - time.time())}


# --- Codes ------------------------------------------------------------------


def _code_key(code: str) -> str:
    return 'telegram:code:' + salted_hmac('accounts.telegram_code', code).hexdigest()


def _user_key(telegram_id: int) -> str:
    return f'telegram:user-code:{telegram_id}'


def issue_code(telegram_id: int, chat_id: int) -> None:
    """Send a fresh code to this Telegram account (replaces its previous code)."""
    previous = cache.get(_user_key(telegram_id))
    now = time.time()
    if previous and previous['resend_at'] > now:
        wait = int(previous['resend_at'] - now) + 1
        _send_quietly(chat_id, f'Your last code is still valid. You can get a new one in {wait} s.')
        return

    ttl = settings.EMAIL_CODE_TTL
    for _ in range(20):  # codes are looked up by value, so they must be unique
        code = f'{secrets.randbelow(10**CODE_LENGTH):0{CODE_LENGTH}d}'
        if cache.add(_code_key(code), {'telegram_id': telegram_id}, ttl):
            break
    else:
        raise TelegramError('Could not issue a code, please try again')

    minutes = max(1, ttl // 60)
    try:
        _api(
            'sendMessage',
            chat_id=chat_id,
            parse_mode='HTML',
            # <code> renders monospace: tapping it copies the code in Telegram apps.
            text=(
                f'Your sign-in code: <code>{code}</code>\n\n'
                f'Enter it on the website. It expires in {minutes} minute'
                f'{"s" if minutes > 1 else ""}. '
                "Don't share it with anyone - if you didn't try to sign in, ignore this message."
            ),
            # One-tap "copy to clipboard" button (Bot API copy_text).
            reply_markup={
                'inline_keyboard': [[{'text': '📋 Copy code', 'copy_text': {'text': code}}]]
            },
        )
    except TelegramError:
        cache.delete(_code_key(code))
        raise

    if previous:
        cache.delete(previous['code_key'])  # only the newest code works
    cache.set(
        _user_key(telegram_id),
        {'code_key': _code_key(code), 'resend_at': now + settings.EMAIL_CODE_RESEND_COOLDOWN},
        ttl,
    )


def verify_login(token: str, code: str) -> SocialProfile:
    """Check the code typed on the website; return the Telegram profile it was sent to."""
    invalid = ProviderError('Invalid or expired code')
    try:
        pending = _load(token)
    except LoginExpired as exc:
        raise invalid from exc

    key = _code_key(code.strip())
    issued = cache.get(key)
    if issued is None:
        pending['attempts'] += 1
        if pending['attempts'] >= MAX_ATTEMPTS:
            cache.delete(_login_key(token))  # too many guesses: start over
        else:
            cache.set(_login_key(token), pending, max(1, pending['expires_at'] - time.time()))
        raise invalid

    # Single use: the code, its owner's record and the page session are spent.
    cache.delete_many([key, _user_key(issued['telegram_id']), _login_key(token)])
    chat = TelegramChat.objects.get(telegram_id=issued['telegram_id'])
    return SocialProfile(
        provider='telegram',
        uid=str(chat.telegram_id),
        first_name=chat.first_name,
        last_name=chat.last_name,
        username_hint=chat.username or f'tg_{chat.telegram_id}',
        extra={'username': chat.username},
    )


# --- Incoming messages ------------------------------------------------------


def sync_updates() -> None:
    """Development mode: pull and process messages the bot received since the last sync."""
    if not cache.add(SYNC_LOCK_KEY, 1, timeout=HTTP_TIMEOUT + 5):
        return  # another request is syncing right now; it will handle the new messages
    try:
        offset = cache.get(OFFSET_KEY)
        params = {'timeout': 0, 'allowed_updates': ['message']}
        if offset:
            params['offset'] = offset
        for update in _api('getUpdates', **params):
            cache.set(OFFSET_KEY, update['update_id'] + 1, timeout=None)
            handle_update(update)
    finally:
        cache.delete(SYNC_LOCK_KEY)


def handle_update(update: dict) -> None:
    """Process one update from Telegram (from getUpdates or the webhook)."""
    message = update.get('message') or {}
    sender, chat = message.get('from'), message.get('chat') or {}
    if not sender or chat.get('type') != 'private' or sender.get('is_bot'):
        return
    _remember(sender, chat['id'])
    _handle_text((message.get('text') or '').strip(), sender['id'], chat['id'])


def _handle_text(text: str, telegram_id: int, chat_id: int) -> None:
    if text.startswith('/start'):
        # Telegram requires Start once per bot: show the button so it's never needed again.
        _send_quietly(
            chat_id,
            f'Welcome! Next time you sign in, just press "{CODE_BUTTON}" below.',
            reply_markup=KEYBOARD,
        )
        issue_code(telegram_id, chat_id)
    elif text in (CODE_BUTTON, '/code'):
        issue_code(telegram_id, chat_id)
    else:
        _send_quietly(
            chat_id, f'To get a sign-in code, press "{CODE_BUTTON}" below.', reply_markup=KEYBOARD
        )


@transaction.atomic
def _remember(sender: dict, chat_id: int) -> None:
    username = (sender.get('username') or '').lower()
    if username:
        # Usernames can move between accounts: only the latest owner keeps it.
        TelegramChat.objects.filter(username=username).exclude(telegram_id=sender['id']).update(
            username=''
        )
    TelegramChat.objects.update_or_create(
        telegram_id=sender['id'],
        defaults={
            'chat_id': chat_id,
            'username': username,
            'first_name': (sender.get('first_name') or '')[:150],
            'last_name': (sender.get('last_name') or '')[:150],
        },
    )
