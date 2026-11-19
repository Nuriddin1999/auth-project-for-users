import hashlib
import hmac
import time
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase

from .models import SocialAccount
from .providers import ProviderError, SocialProfile

User = get_user_model()
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
        verify.return_value = google_profile()
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


class MockModeTests(APITestCase):
    @override_settings(DEBUG=True, SOCIAL_AUTH_MOCK=True)
    def test_mock_login_and_linking(self):
        g = self.client.post('/api/auth/google/', {'mock': True}, format='json')
        self.assertEqual(g.status_code, 201, g.data)
        fb = self.client.post('/api/auth/facebook/', {'mock': True}, format='json')
        self.assertEqual(fb.data['user']['id'], g.data['user']['id'])  # same verified email
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {fb.data["access"]}')
        tg = self.client.post('/api/auth/telegram/', {'mock': True}, format='json')
        self.assertEqual(tg.status_code, 200, tg.data)
        self.assertEqual(len(tg.data['user']['social_accounts']), 3)

    @override_settings(DEBUG=True, SOCIAL_AUTH_MOCK=False)
    def test_mock_ignored_when_disabled(self):
        res = self.client.post('/api/auth/google/', {'mock': True}, format='json')
        self.assertEqual(res.status_code, 400)  # falls through to normal validation

    @override_settings(DEBUG=False, SOCIAL_AUTH_MOCK=True)
    def test_mock_refused_without_debug(self):
        res = self.client.post('/api/auth/google/', {'mock': True}, format='json')
        self.assertEqual(res.status_code, 401)
        self.assertFalse(User.objects.exists())
