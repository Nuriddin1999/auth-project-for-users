import hashlib
import hmac
import time
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase as BaseAPITestCase

from .models import SocialAccount
from .providers import ProviderError, SocialProfile

User = get_user_model()


# Real password hashing is slow on purpose; tests don't need that.
@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class APITestCase(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        cache.clear()  # reset rate-limit counters between tests


BOT_TOKEN = '123456:TEST-TOKEN'


def signed_telegram_payload(**overrides):
    data = {
        'id': 42,
        'first_name': 'Ivan',
        'username': 'ivan_tg',
        'auth_date': int(time.time()),
        **overrides,
    }
    check = '\n'.join(f'{k}={data[k]}' for k in sorted(data))
    secret = hashlib.sha256(BOT_TOKEN.encode()).digest()
    data['hash'] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return data


@override_settings(TELEGRAM_BOT_TOKEN=BOT_TOKEN)
class TelegramLoginTests(APITestCase):
    url = '/api/auth/telegram/'

    def test_valid_login_creates_user(self):
        res = self.client.post(self.url, signed_telegram_payload(), format='json')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertIn('access', res.data)
        self.assertNotIn('refresh', res.data)  # refresh token is only in the httpOnly cookie
        self.assertEqual(res.data['user']['username'], 'ivan_tg')
        self.assertTrue(SocialAccount.objects.filter(provider='telegram', uid='42').exists())

    def test_second_login_returns_same_user(self):
        first = self.client.post(self.url, signed_telegram_payload(), format='json')
        second = self.client.post(self.url, signed_telegram_payload(), format='json')
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data['user']['id'], second.data['user']['id'])
        self.assertEqual(User.objects.count(), 1)

    def test_tampered_payload_rejected(self):
        payload = signed_telegram_payload()
        payload['id'] = 43
        res = self.client.post(self.url, payload, format='json')
        self.assertEqual(res.status_code, 401)

    def test_whitespace_in_name_kept_for_hash(self):
        res = self.client.post(
            self.url, signed_telegram_payload(first_name=' Ivan '), format='json'
        )
        self.assertEqual(res.status_code, 201, res.data)

    def test_expired_payload_rejected(self):
        payload = signed_telegram_payload(auth_date=int(time.time()) - 2 * 86400)
        res = self.client.post(self.url, payload, format='json')
        self.assertEqual(res.status_code, 401)

    @override_settings(TELEGRAM_BOT_TOKEN='')
    def test_not_configured(self):
        res = self.client.post(self.url, signed_telegram_payload(), format='json')
        self.assertEqual(res.status_code, 503)


def google_profile(**kw):
    return SocialProfile(
        **{
            'provider': 'google',
            'uid': 'g-1',
            'email': 'ivan@example.com',
            'email_verified': True,
            'first_name': 'Ivan',
            'username_hint': 'ivan',
            **kw,
        }
    )


class GoogleAndLinkingTests(APITestCase):
    url = '/api/auth/google/'

    @mock.patch('accounts.providers.verify_google')
    def test_google_login(self, verify):
        verify.return_value = google_profile()
        res = self.client.post(self.url, {'credential': 'x'}, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['user']['email'], 'ivan@example.com')

    @mock.patch('accounts.providers.verify_google')
    def test_invalid_google_token(self, verify):
        verify.side_effect = ProviderError('bad')
        res = self.client.post(self.url, {'credential': 'x'}, format='json')
        self.assertEqual(res.status_code, 401)

    @mock.patch('accounts.providers.verify_facebook')
    @mock.patch('accounts.providers.verify_google')
    def test_verified_email_links_accounts(self, verify_g, verify_fb):
        verify_g.return_value = google_profile()
        verify_fb.return_value = SocialProfile(
            provider='facebook',
            uid='fb-1',
            email='IVAN@example.com',
            email_verified=True,
        )
        g = self.client.post(self.url, {'credential': 'x'}, format='json')
        fb = self.client.post('/api/auth/facebook/', {'access_token': 'y'}, format='json')
        self.assertEqual(g.data['user']['id'], fb.data['user']['id'])
        self.assertEqual(User.objects.count(), 1)

    @mock.patch('accounts.providers.verify_google')
    def test_unverified_email_does_not_link(self, verify):
        User.objects.create_user('victim', email='ivan@example.com', password='pw-12345678')
        verify.return_value = google_profile(email_verified=False)
        res = self.client.post(self.url, {'credential': 'x'}, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertNotEqual(res.data['user']['username'], 'victim')

    @override_settings(TELEGRAM_BOT_TOKEN=BOT_TOKEN)
    @mock.patch('accounts.providers.verify_google')
    def test_logged_in_user_can_connect_telegram_and_disconnect(self, verify):
        # No email -> no email-code sign-in, so the last provider can't be removed.
        verify.return_value = google_profile(email='', email_verified=False)
        access = self.client.post(self.url, {'credential': 'x'}, format='json').data['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')

        res = self.client.post('/api/auth/telegram/', signed_telegram_payload(), format='json')
        self.assertEqual(res.status_code, 200, res.data)
        me = self.client.get('/api/auth/me/').data
        self.assertEqual({a['provider'] for a in me['social_accounts']}, {'google', 'telegram'})

        self.assertEqual(self.client.delete('/api/auth/social/telegram/').status_code, 200)
        # The last remaining login method cannot be removed.
        self.assertEqual(self.client.delete('/api/auth/social/google/').status_code, 400)

    @override_settings(TELEGRAM_BOT_TOKEN=BOT_TOKEN)
    @mock.patch('accounts.providers.verify_google')
    def test_cannot_steal_account_linked_to_other_user(self, verify):
        self.client.post('/api/auth/telegram/', signed_telegram_payload(), format='json')
        verify.return_value = google_profile(email='other@example.com', uid='g-2')
        access = self.client.post(self.url, {'credential': 'x'}, format='json').data['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        res = self.client.post('/api/auth/telegram/', signed_telegram_payload(), format='json')
        self.assertEqual(res.status_code, 409)


class FacebookVerifierTests(APITestCase):
    @override_settings(FACEBOOK_APP_ID='111', FACEBOOK_APP_SECRET='secret')
    @mock.patch('accounts.providers.requests.get')
    def test_token_for_other_app_rejected(self, get):
        get.return_value.json.return_value = {
            'data': {'is_valid': True, 'app_id': '999', 'user_id': '1'}
        }
        res = self.client.post('/api/auth/facebook/', {'access_token': 't'}, format='json')
        self.assertEqual(res.status_code, 401)

    @override_settings(FACEBOOK_APP_ID='111', FACEBOOK_APP_SECRET='secret')
    @mock.patch('accounts.providers.requests.get')
    def test_valid_facebook_login(self, get):
        debug = mock.Mock(
            **{'json.return_value': {'data': {'is_valid': True, 'app_id': '111', 'user_id': '77'}}}
        )
        me = mock.Mock(
            status_code=200,
            **{
                'json.return_value': {
                    'id': '77',
                    'first_name': 'Ivan',
                    'email': 'ivan@fb.com',
                    'picture': {'data': {'url': 'https://example.com/a.jpg'}},
                }
            },
        )
        get.side_effect = [debug, me]
        res = self.client.post('/api/auth/facebook/', {'access_token': 't'}, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['user']['avatar_url'], 'https://example.com/a.jpg')


@override_settings(TELEGRAM_BOT_TOKEN=BOT_TOKEN)
class TokenTests(APITestCase):
    def test_me_requires_auth(self):
        self.assertEqual(self.client.get('/api/auth/me/').status_code, 401)

    def login(self):
        return self.client.post('/api/auth/telegram/', signed_telegram_payload(), format='json')

    def test_refresh_cookie_is_httponly(self):
        cookie = self.login().cookies['refresh_token']
        self.assertTrue(cookie['httponly'])
        self.assertEqual(cookie['samesite'], 'Lax')
        self.assertEqual(cookie['path'], '/api/auth/')

    def test_refresh_uses_cookie_and_rotates(self):
        old = self.login().cookies['refresh_token'].value
        res = self.client.post('/api/auth/token/refresh/')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertIn('access', res.data)
        self.assertNotIn('refresh', res.data)
        new = res.cookies['refresh_token'].value
        self.assertNotEqual(old, new)

        # The rotated-out token is blacklisted and can't be reused.
        self.client.cookies['refresh_token'] = old
        self.assertEqual(self.client.post('/api/auth/token/refresh/').status_code, 401)

    def test_refresh_without_cookie(self):
        self.assertEqual(self.client.post('/api/auth/token/refresh/').status_code, 401)

    def test_logout_blacklists_refresh(self):
        old = self.login().cookies['refresh_token'].value
        res = self.client.post('/api/auth/logout/')
        self.assertEqual(res.status_code, 204)
        self.assertEqual(res.cookies['refresh_token'].value, '')  # cookie removed

        self.client.cookies['refresh_token'] = old
        self.assertEqual(self.client.post('/api/auth/token/refresh/').status_code, 401)


MOCK = {'DEBUG': True, 'SOCIAL_AUTH_MOCK': True, 'SOCIAL_AUTH_MOCK_CODE': '12345'}


@override_settings(**MOCK)
class MockModeTests(APITestCase):
    def mock_login(self, provider, identity, code='12345'):
        start = self.client.post(
            f'/api/auth/{provider}/', {'mock': True, 'identity': identity}, format='json'
        )
        self.assertEqual(start.status_code, 200, start.data)
        data = {'mock': True, 'identity': identity, 'code': code}
        return start, self.client.post(f'/api/auth/{provider}/', data, format='json')

    def test_google_asks_email_then_code(self):
        start, res = self.mock_login('google', 'Anna.Smith@Example.com')
        self.assertEqual(start.data['channel'], 'email')
        self.assertEqual(start.data['code_length'], 5)
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['user']['email'], 'anna.smith@example.com')
        self.assertEqual(res.data['user']['social_accounts'][0]['provider'], 'google')

    def test_telegram_asks_username_then_code(self):
        start, res = self.mock_login('telegram', '@Ivan_Petrov')
        self.assertEqual(start.data['channel'], 'telegram')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['user']['username'], 'ivan_petrov')
        self.assertEqual(res.data['user']['email'], '')

    def test_wrong_code_rejected(self):
        _, res = self.mock_login('google', 'anna@example.com', code='11111')
        self.assertEqual(res.status_code, 401)
        self.assertFalse(User.objects.exists())

    def test_code_without_start_rejected(self):
        data = {'mock': True, 'identity': 'anna@example.com', 'code': '12345'}
        self.assertEqual(
            self.client.post('/api/auth/google/', data, format='json').status_code, 401
        )

    def test_code_works_once(self):
        self.mock_login('google', 'anna@example.com')
        data = {'mock': True, 'identity': 'anna@example.com', 'code': '12345'}
        self.assertEqual(
            self.client.post('/api/auth/google/', data, format='json').status_code, 401
        )

    def test_invalid_identity(self):
        for provider, identity in [
            ('google', 'not-an-email'),
            ('telegram', 'ab'),
            ('telegram', '1abcde'),
        ]:
            res = self.client.post(
                f'/api/auth/{provider}/', {'mock': True, 'identity': identity}, format='json'
            )
            self.assertEqual(res.status_code, 400, identity)

    def test_five_wrong_codes_reset_verification(self):
        self.client.post(
            '/api/auth/google/', {'mock': True, 'identity': 'a@example.com'}, format='json'
        )
        for _ in range(5):
            data = {'mock': True, 'identity': 'a@example.com', 'code': '00000'}
            self.client.post('/api/auth/google/', data, format='json')
        data = {'mock': True, 'identity': 'a@example.com', 'code': '12345'}
        self.assertEqual(
            self.client.post('/api/auth/google/', data, format='json').status_code, 401
        )

    def test_same_email_merges_google_and_facebook_and_telegram_links(self):
        _, g = self.mock_login('google', 'anna@example.com')
        _, fb = self.mock_login('facebook', 'anna@example.com')
        self.assertEqual(fb.data['user']['id'], g.data['user']['id'])  # same verified email
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {fb.data["access"]}')
        _, tg = self.mock_login('telegram', 'anna_tg')
        self.assertEqual(tg.status_code, 200, tg.data)
        self.assertEqual(len(tg.data['user']['social_accounts']), 3)

    @override_settings(SOCIAL_AUTH_MOCK=False)
    def test_mock_ignored_when_disabled(self):
        data = {'mock': True, 'identity': 'a@b.co'}
        res = self.client.post('/api/auth/google/', data, format='json')
        self.assertEqual(res.status_code, 400)  # falls through to normal validation
        self.assertIn('credential', res.data)

    @override_settings(DEBUG=False)
    def test_mock_refused_without_debug(self):
        start = {'mock': True, 'identity': 'a@b.co'}
        res = self.client.post('/api/auth/google/', start, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data['detail'], 'Test mode is disabled')
        res = self.client.post('/api/auth/google/', {**start, 'code': '12345'}, format='json')
        self.assertEqual(res.status_code, 401)
        self.assertFalse(User.objects.exists())


class EmailAuthTests(APITestCase):
    PASSWORD = 'Str0ng-pass-42'

    def last_code(self):
        from django.core import mail

        return mail.outbox[-1].subject.split()[0]

    def signup(self, name='Ivan Petrov', email='ivan@example.com', password=None, confirm=None):
        password = password or self.PASSWORD
        data = {
            'name': name,
            'email': email,
            'password': password,
            'password_confirm': confirm or password,
        }
        return self.client.post('/api/auth/email/signup/', data)

    def verify(self, code, email='ivan@example.com'):
        return self.client.post('/api/auth/email/verify/', {'email': email, 'code': code})

    def login(self, email='ivan@example.com', password=None):
        data = {'email': email, 'password': password or self.PASSWORD}
        return self.client.post('/api/auth/login/', data)

    # --- sign up ------------------------------------------------------------

    def test_signup_flow_creates_user_with_password(self):
        self.assertEqual(self.signup(email='Ivan@Example.com ').status_code, 200)
        res = self.verify(self.last_code())
        self.assertEqual(res.status_code, 201, res.data)
        self.assertTrue(res.data['created'])
        self.assertEqual(res.data['email'], 'ivan@example.com')
        user = User.objects.get()
        self.assertEqual((user.first_name, user.last_name), ('Ivan', 'Petrov'))
        self.assertTrue(user.check_password(self.PASSWORD))

    def test_signup_does_not_sign_in(self):
        self.signup()
        res = self.verify(self.last_code())
        # Registration only creates the account; the user signs in afterwards.
        self.assertNotIn('access', res.data)
        self.assertNotIn('refresh_token', res.cookies)
        self.assertEqual(self.client.post('/api/auth/token/refresh/').status_code, 401)

        res = self.login()
        self.assertEqual(res.status_code, 200, res.data)
        self.assertTrue(res.data['user']['has_password'])
        self.assertIn('refresh_token', res.cookies)

    def test_no_account_before_email_is_confirmed(self):
        self.signup()
        self.assertFalse(User.objects.exists())
        self.assertEqual(self.login().status_code, 401)

    def test_password_is_not_stored_in_plain_text(self):
        from .models import EmailCode

        self.signup()
        record = EmailCode.objects.get()
        self.assertNotIn(self.PASSWORD, record.password_hash)
        self.assertNotIn(self.last_code(), record.code_hash)

    def test_passwords_must_match(self):
        res = self.signup(password='Str0ng-pass-42', confirm='Str0ng-pass-43')
        self.assertEqual(res.status_code, 400)
        self.assertIn('password_confirm', res.data)

    def test_weak_password_rejected(self):
        for weak in ['12345678', 'password', 'short1!', 'ivanpetrov1']:
            res = self.signup(password=weak)
            self.assertEqual(res.status_code, 400, weak)
            self.assertIn('password', res.data)

    def test_signup_with_existing_email_is_rejected(self):
        User.objects.create_user('ivan', email='ivan@example.com')
        res = self.signup()
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data['code'], 'account_exists')

    def test_code_works_only_once(self):
        self.signup()
        code = self.last_code()
        self.assertEqual(self.verify(code).status_code, 201)
        self.assertEqual(self.verify(code).status_code, 400)

    def test_wrong_attempts_burn_the_code(self):
        self.signup()
        code = self.last_code()
        wrong = '000000' if code != '000000' else '111111'
        for _ in range(5):
            self.assertEqual(self.verify(wrong).status_code, 400)
        # Even the correct code no longer works: brute force is capped at 5 guesses.
        self.assertEqual(self.verify(code).status_code, 400)
        self.assertFalse(User.objects.exists())

    def test_expired_code_rejected(self):
        from datetime import timedelta

        from django.utils import timezone

        from .models import EmailCode

        self.signup()
        EmailCode.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.verify(self.last_code()).status_code, 400)

    def test_resend_cooldown_and_new_code_invalidates_old(self):
        from .models import EmailCode

        self.signup()
        old = self.last_code()
        res = self.signup()
        self.assertEqual(res.status_code, 429)
        self.assertIn('Retry-After', res)

        EmailCode.objects.update(created_at=EmailCode.objects.get().created_at.replace(year=2000))
        self.assertEqual(self.signup().status_code, 200)
        new = self.last_code()
        if old != new:
            self.assertEqual(self.verify(old).status_code, 400)
        self.assertEqual(self.verify(new).status_code, 201)

    def test_hourly_limit(self):
        from .models import EmailCode

        for _ in range(5):
            self.assertEqual(self.signup().status_code, 200)
            EmailCode.objects.update(used_at=EmailCode.objects.first().created_at)  # skip cooldown
        res = self.signup()
        self.assertEqual(res.status_code, 429)
        self.assertEqual(res.data['code'], 'hourly_limit')

    def test_email_has_html_and_text_versions(self):
        from django.core import mail

        self.signup()
        message = mail.outbox[-1]
        code = self.last_code()
        self.assertIn(code, message.body)
        html, mimetype = message.alternatives[0]
        self.assertEqual(mimetype, 'text/html')
        self.assertIn(code, html)
        self.assertIn('Ivan Petrov', html)

    def test_smtp_failure_returns_503_and_keeps_previous_code(self):
        import smtplib

        from .models import EmailCode

        self.signup()
        old = self.last_code()
        EmailCode.objects.update(created_at=EmailCode.objects.get().created_at.replace(year=2000))
        with (
            self.assertLogs('accounts.email_codes', 'ERROR'),
            mock.patch('accounts.email_codes.send_mail', side_effect=smtplib.SMTPException),
        ):
            res = self.signup()
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.data['code'], 'email_failed')
        self.assertEqual(EmailCode.objects.count(), 1)  # nothing saved for the failed send
        self.assertEqual(self.verify(old).status_code, 201)  # the previous code still works

    @mock.patch('accounts.providers.verify_google')
    def test_email_signup_then_google_merges_by_verified_email(self, verify):
        self.signup()
        self.verify(self.last_code())
        verify.return_value = google_profile()  # same verified email ivan@example.com
        res = self.client.post('/api/auth/google/', {'credential': 'x'}, format='json')
        self.assertEqual(res.data['user']['id'], User.objects.get(email='ivan@example.com').id)

    @override_settings(TELEGRAM_BOT_TOKEN=BOT_TOKEN)
    def test_user_with_email_can_disconnect_last_social_account(self):
        self.signup()
        self.verify(self.last_code())
        access = self.login().data['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        self.client.post('/api/auth/telegram/', signed_telegram_payload(), format='json')
        self.assertEqual(self.client.delete('/api/auth/social/telegram/').status_code, 200)

    def test_resend_reuses_name_and_password(self):
        from .models import EmailCode

        self.signup()
        EmailCode.objects.update(created_at=EmailCode.objects.get().created_at.replace(year=2000))
        data = {'email': 'ivan@example.com', 'purpose': 'signup'}
        self.assertEqual(self.client.post('/api/auth/email/resend/', data).status_code, 200)
        res = self.verify(self.last_code())
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(User.objects.get().first_name, 'Ivan')
        self.assertTrue(User.objects.get().check_password(self.PASSWORD))

    def test_resend_without_signup(self):
        data = {'email': 'ivan@example.com', 'purpose': 'signup'}
        res = self.client.post('/api/auth/email/resend/', data)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data['code'], 'signup_required')

    # --- sign in with password ---------------------------------------------

    def create_user(self, password=None):
        return User.objects.create_user(
            'ivan', email='ivan@example.com', password=password or self.PASSWORD
        )

    def test_login_with_password(self):
        user = self.create_user()
        res = self.login(email='IVAN@example.com')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['user']['id'], user.id)
        self.assertFalse(res.data['created'])
        self.assertIn('refresh_token', res.cookies)

    def test_login_wrong_password_and_unknown_email_look_the_same(self):
        self.create_user()
        wrong = self.login(password='wrong-password')
        unknown = self.login(email='nobody@example.com')
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(unknown.status_code, 401)
        self.assertEqual(wrong.data, unknown.data)  # doesn't reveal which emails exist

    def test_login_without_password_set(self):
        User.objects.create_user('ivan', email='ivan@example.com')  # e.g. signed up via Google
        self.assertEqual(self.login().status_code, 401)

    def test_login_is_rate_limited(self):
        self.create_user()
        statuses = [self.login(password='wrong').status_code for _ in range(11)]
        self.assertEqual(statuses[-1], 429)

    def test_login_limit_is_not_used_up_by_other_auth_requests(self):
        self.create_user()
        for _ in range(12):  # e.g. sign-up attempts, social logins, code requests
            self.client.post('/api/auth/email/signup/', {})
        self.assertEqual(self.login().status_code, 200)

    # --- forgot password ----------------------------------------------------

    def request_reset(self, email='ivan@example.com'):
        return self.client.post('/api/auth/password/reset/', {'email': email})

    def verify_reset(self, code, email='ivan@example.com'):
        return self.client.post('/api/auth/password/reset/verify/', {'email': email, 'code': code})

    def confirm_reset(self, token, password='N3w-secret-pass', confirm=None):
        data = {'token': token, 'password': password, 'password_confirm': confirm or password}
        return self.client.post('/api/auth/password/reset/confirm/', data)

    def test_reset_password_flow(self):
        self.create_user()
        self.assertEqual(self.request_reset().status_code, 200)
        res = self.verify_reset(self.last_code())
        self.assertEqual(res.status_code, 200, res.data)
        res = self.confirm_reset(res.data['reset_token'])
        self.assertEqual(res.status_code, 200, res.data)
        self.assertIn('access', res.data)  # signed in right away

        self.assertEqual(self.login(password='N3w-secret-pass').status_code, 200)
        self.assertEqual(self.login().status_code, 401)  # old password no longer works

    def test_reset_lets_social_only_user_set_a_password(self):
        User.objects.create_user('ivan', email='ivan@example.com')  # no password
        self.request_reset()
        token = self.verify_reset(self.last_code()).data['reset_token']
        self.assertEqual(self.confirm_reset(token).status_code, 200)
        self.assertEqual(self.login(password='N3w-secret-pass').status_code, 200)

    def test_reset_unknown_email(self):
        res = self.request_reset('nobody@example.com')
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.data['code'], 'account_not_found')

    def test_reset_wrong_code(self):
        self.create_user()
        self.request_reset()
        wrong = '000000' if self.last_code() != '000000' else '111111'
        self.assertEqual(self.verify_reset(wrong).status_code, 400)

    def test_signup_code_cannot_be_used_for_reset(self):
        self.signup(email='other@example.com')
        code = self.last_code()
        self.create_user()
        self.assertEqual(self.verify_reset(code, email='other@example.com').status_code, 400)

    def test_reset_token_is_one_time(self):
        self.create_user()
        self.request_reset()
        token = self.verify_reset(self.last_code()).data['reset_token']
        self.assertEqual(self.confirm_reset(token).status_code, 200)
        res = self.confirm_reset(token, password='An0ther-pass-99')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data['code'], 'invalid_token')

    def test_reset_token_tampered(self):
        self.assertEqual(self.confirm_reset('garbage').status_code, 400)

    def test_reset_validates_new_password(self):
        self.create_user()
        self.request_reset()
        token = self.verify_reset(self.last_code()).data['reset_token']
        self.assertEqual(self.confirm_reset(token, password='12345678').status_code, 400)
        res = self.confirm_reset(token, password='N3w-secret-pass', confirm='different-1')
        self.assertIn('password_confirm', res.data)

    def test_reset_signs_out_other_sessions(self):
        self.create_user()
        old_refresh = self.login().cookies['refresh_token'].value
        self.request_reset()
        token = self.verify_reset(self.last_code()).data['reset_token']
        self.confirm_reset(token)
        self.client.cookies['refresh_token'] = old_refresh
        self.assertEqual(self.client.post('/api/auth/token/refresh/').status_code, 401)


class EmailTestCodeTests(APITestCase):
    SIGNUP = {
        'name': 'Anna',
        'email': 'anna@example.com',
        'password': 'Str0ng-pass-42',
        'password_confirm': 'Str0ng-pass-42',
    }

    @override_settings(DEBUG=True, EMAIL_TEST_CODE='12345')
    def test_fixed_code_creates_account_without_sending_email(self):
        from django.core import mail

        with self.assertLogs('accounts.email_codes', 'WARNING'):
            res = self.client.post('/api/auth/email/signup/', self.SIGNUP)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['code_length'], 5)
        self.assertEqual(res.data['expires_in'], 60)
        self.assertEqual(len(mail.outbox), 0)

        data = {'email': 'anna@example.com', 'code': '12345'}
        res = self.client.post('/api/auth/email/verify/', data)
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(User.objects.get().first_name, 'Anna')

    @override_settings(DEBUG=True, EMAIL_TEST_CODE='12345')
    def test_fixed_code_works_for_password_reset(self):
        User.objects.create_user('anna', email='anna@example.com', password='Old-pass-123')
        with self.assertLogs('accounts.email_codes', 'WARNING'):
            self.client.post('/api/auth/password/reset/', {'email': 'anna@example.com'})
        data = {'email': 'anna@example.com', 'code': '12345'}
        res = self.client.post('/api/auth/password/reset/verify/', data)
        self.assertEqual(res.status_code, 200, res.data)
        self.assertIn('reset_token', res.data)

    @override_settings(DEBUG=False, EMAIL_TEST_CODE='12345')
    def test_fixed_code_ignored_without_debug(self):
        from django.core import mail

        res = self.client.post('/api/auth/email/signup/', self.SIGNUP)
        self.assertEqual(res.data['code_length'], 6)
        self.assertEqual(len(mail.outbox), 1)  # a real random code is emailed
        data = {'email': 'anna@example.com', 'code': '12345'}
        self.assertEqual(self.client.post('/api/auth/email/verify/', data).status_code, 400)
