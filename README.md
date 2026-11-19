# Auth: Google / Telegram / Facebook

Вход через социальные сети: **React + TypeScript (Vite)** на фронтенде,
**Django REST Framework + JWT (SimpleJWT)** на бэкенде.

## Быстрый старт

```bash
# backend  (http://localhost:8000)
cd backend
py -m venv venv                       # macOS/Linux: python3 -m venv venv
venv\Scripts\pip install -r requirements.txt
copy .env.example .env                # macOS/Linux: cp
venv\Scripts\python manage.py migrate
venv\Scripts\python manage.py runserver

# frontend  (http://localhost:5173)
cd frontend
npm install
copy .env.example .env
npm run dev
```

### Тестовый режим (без ключей провайдеров)

Чтобы проверить приложение, не регистрируя приложения в Google, Facebook и Telegram, включите:

```env
# backend/.env
SOCIAL_AUTH_MOCK=True
# frontend/.env
VITE_MOCK_AUTH=true
```

Кнопки провайдеров, для которых не заданы ключи, будут входить под тестовыми пользователями
без обращения к провайдеру. Вся остальная логика настоящая: создание пользователя, JWT,
привязка/отвязка аккаунтов, refresh, logout. Режим работает **только при `DEBUG=True`**:
с выключенным DEBUG бэкенд отклоняет такие запросы (покрыто тестом).

Тестовые профили Google и Facebook имеют одинаковый подтверждённый email, поэтому
объединяются в одного пользователя, так видно, как работает связывание аккаунтов.

Как только для провайдера задан реальный ключ, его кнопка автоматически работает по-настоящему.

## Как это устроено

```
Браузер ──(1) вход у провайдера──▶ Google / Facebook / Telegram
   │                                        │
   │◀──────── ID token / access token / подписанные данные
   │
   └──(2) POST /api/auth/<provider>/ ──▶ Django
                                          ├─ (3) проверка у провайдера / проверка подписи
                                          ├─ (4) поиск или создание пользователя
                                          └─ (5) access token в JSON + refresh token в httpOnly cookie
```

| Провайдер | Что присылает фронтенд | Как проверяет бэкенд |
|---|---|---|
| Google | ID token (JWT) от Google Identity Services | подпись по публичным ключам Google, `aud` = наш Client ID, `iss` |
| Facebook | user access token из JS SDK | `debug_token`: токен валиден и выдан **нашему** приложению; профиль запрашивается с `appsecret_proof` |
| Telegram | данные из Login Widget | HMAC-SHA256 с ключом `SHA256(bot_token)`, сравнение за константное время, `auth_date` не старше 24 ч |

### API

| Метод | URL | Описание |
|---|---|---|
| POST | `/api/auth/google/` | `{credential}` |
| POST | `/api/auth/facebook/` | `{access_token}` |
| POST | `/api/auth/telegram/` | объект `user` из Telegram widget без изменений |
| POST | `/api/auth/token/refresh/` | refresh из cookie → новый access (refresh ротируется) |
| POST | `/api/auth/logout/` | refresh из cookie → blacklist, cookie удаляется |
| GET/PATCH | `/api/auth/me/` | текущий пользователь |
| DELETE | `/api/auth/social/<provider>/` | отвязать провайдера |
| GET | `/api/auth/providers/` | какие провайдеры настроены |

Ответ на вход: `{access, user, created}`, refresh token приходит только в cookie.

## Архитектурные решения

**Проверка только на сервере.** Фронтенд никогда не присылает «готовый профиль», только
то, что подписал провайдер. Бэкенд сам проверяет подпись или токен и лишь потом доверяет данным.

**Хранение токенов.**
- *Access token* (15 мин) хранится только в памяти JS-модуля, не в `localStorage`.
- *Refresh token* (7 дней) лежит в cookie `HttpOnly; SameSite=Lax; Path=/api/auth/`
  (+ `Secure` вне DEBUG). JavaScript, а значит и XSS, его прочитать не может.
- После перезагрузки страницы фронтенд восстанавливает сессию запросом `/token/refresh/`.
- `SameSite=Lax` не даёт браузеру отправить cookie в межсайтовом POST, это защита
  cookie-эндпоинтов от CSRF. Остальные эндпоинты авторизуются заголовком `Authorization`,
  который браузер сам не подставляет.
- Refresh ротируется при каждом использовании, старый попадает в blacklist, поэтому украденный
  и уже использованный refresh-токен бесполезен.

**Связывание аккаунтов.**
- Повторный вход тем же провайдером → тот же пользователь (`SocialAccount(provider, uid)` уникален).
- Залогиненный пользователь, входящий через другого провайдера → провайдер привязывается к нему.
- Совпадение email → объединение **только если провайдер подтвердил email** (Google
  `email_verified`, Facebook отдаёт только подтверждённые). Иначе можно было бы захватить
  чужой аккаунт, зарегистрировавшись у провайдера с чужим email.
- Нельзя привязать аккаунт, уже привязанный к другому пользователю (409), и нельзя
  отвязать последний способ входа (400).

**Прочее.** Rate limit на эндпоинты входа (30/мин с IP); пользователь и социальный аккаунт
создаются в одной транзакции; гонка при одновременной привязке обрабатывается через
уникальный индекс.

## Структура

```
backend/
  config/settings.py        настройки, всё секретное — из .env
  accounts/
    providers.py            проверка Google / Facebook / Telegram (+ тестовые профили)
    services.py             поиск / создание / связывание пользователя, выдача JWT
    cookies.py              httpOnly refresh cookie
    views.py, urls.py       API
    models.py               SocialAccount
    tests.py                тесты
frontend/src/
  api/client.ts             axios: access token, авто-refresh при 401
  auth/                     AuthContext, хранение access token в памяти
  components/               кнопки провайдеров
  pages/                    вход, профиль (привязка/отвязка способов входа)
  types.ts                  типы API
```

## Проверки

```bash
# backend
venv\Scripts\python manage.py test accounts   # 22 теста
venv\Scripts\ruff check . && venv\Scripts\ruff format --check .

# frontend
npm run typecheck
npm run lint
npm run format:check
npm run build                                  # включает проверку типов
```

## Получение ключей

### Google
1. https://console.cloud.google.com/ → APIs & Services → **OAuth consent screen**: настроить,
   в *Test users* добавить свой аккаунт.
2. Credentials → Create credentials → **OAuth client ID** → *Web application*.
3. *Authorized JavaScript origins*: `http://localhost:5173` и `http://localhost`.
4. Client ID → `GOOGLE_CLIENT_ID` (backend) и `VITE_GOOGLE_CLIENT_ID` (frontend). Secret не нужен.

### Facebook
1. https://developers.facebook.com/apps → Create app → use case *Facebook Login*.
2. Добавить разрешение `email`; в настройках Facebook Login → *Allowed Domains for the JavaScript SDK* — `localhost`.
3. Settings → Basic: App ID → `FACEBOOK_APP_ID` + `VITE_FACEBOOK_APP_ID`,
   App Secret → `FACEBOOK_APP_SECRET` (**только backend**).
4. В режиме Development войти могут только пользователи с ролью в приложении; в проде нужен HTTPS.

### Telegram
1. [@BotFather](https://t.me/BotFather): `/newbot` → токен → `TELEGRAM_BOT_TOKEN` (**только backend**).
2. Username бота без `@` → `VITE_TELEGRAM_BOT_NAME`.
3. `/setdomain` → домен сайта. **localhost Telegram не принимает**: для разработки нужен туннель
   (`npx cloudflared tunnel --url http://localhost:5173`); его домен нужно добавить в
   `/setdomain`, `CORS_ALLOWED_ORIGINS` и `server.allowedHosts` в `vite.config.ts`.

## Перед продакшеном

- Свой `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=False`, `SOCIAL_AUTH_MOCK=False`, `DJANGO_ALLOWED_HOSTS`.
- HTTPS (cookie получит флаг `Secure` автоматически).
- Фронтенд и API на одном сайте (например `example.com` и `api.example.com`), иначе
  `SameSite=Lax` cookie не будет отправляться; для разных сайтов нужен `SameSite=None` + CSRF-токен.
- PostgreSQL вместо SQLite.
