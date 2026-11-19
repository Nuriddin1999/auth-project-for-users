# Auth: Google / Telegram / Facebook / Email

Регистрация и вход через социальные сети и по email + паролю (email подтверждается кодом).
**React + TypeScript (Vite)** на фронтенде, **Django REST Framework + JWT (SimpleJWT)** на бэкенде.

| Страница | Что есть |
|---|---|
| `/signup` | имя, email, пароль, подтверждение → `/verify` (код) → аккаунт создан → `/login` (email подставлен) → вход; или Google / Facebook / Telegram |
| `/login` | Google / Facebook / Telegram **или** email + пароль → вход; ссылка «Forgot password?» |
| `/forgot-password` | email → `/verify` (код) → `/reset-password` (новый пароль) → вход |
| `/` | профиль: способы входа (подключить/отключить), пароль (задать/сменить), выход |

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

### Тестовый код (без SMTP)

```env
# backend/.env (работает только при DEBUG=True)
EMAIL_TEST_CODE=12345
```

Письма не отправляются, любой код подтверждения равен `12345`: при регистрации и при сбросе
пароля на странице `/verify` введите `12345`. Уберите переменную, чтобы вернуть настоящие
6-значные коды по почте. С `DEBUG=False` переменная игнорируется (покрыто тестом).

### Где взять код из письма при разработке

Если `EMAIL_HOST` не задан, письма не отправляются, а **печатаются в консоль `runserver`**:

```
Subject: 281632 is your verification code
...
Your code to finish signing up: 281632
```

### Реальная отправка писем (Gmail)

1. Включите двухэтапную проверку в аккаунте Google.
2. Создайте пароль приложения: https://myaccount.google.com/apppasswords (16 символов).
3. В `backend/.env`:
   ```env
   EMAIL_HOST=smtp.gmail.com
   EMAIL_HOST_USER=you@gmail.com
   EMAIL_HOST_PASSWORD=abcdefghijklmnop   # пароль приложения, без пробелов
   ```
4. Перезапустите `runserver` и проверьте: `venv\Scripts\python manage.py sendtestemail you@gmail.com`.

Подходит любой SMTP: Яндекс (`smtp.yandex.ru`, 465, `EMAIL_USE_SSL=True`), Mail.ru, SendGrid, Mailgun.
Письмо отправляется **до** сохранения кода: если SMTP недоступен, API вернёт `503 email_failed`,
код не сохранится, лимиты не потратятся, а предыдущий код продолжит работать. Таймаут SMTP: 10 с.

В продакшене отправку стоит вынести в очередь (Celery/RQ), чтобы запрос не ждал SMTP.

### Тестовый режим (без ключей провайдеров)

Чтобы проверить приложение, не регистрируя приложения в Google, Facebook и Telegram, включите:

```env
# backend/.env
SOCIAL_AUTH_MOCK=True
# frontend/.env
VITE_MOCK_AUTH=true
```

Кнопки провайдеров, для которых не заданы ключи, имитируют вход у провайдера:

- **Google / Facebook:** страница `/connect/google` просит email → «код отправлен» → ввод кода → «Authentication successful».
- **Telegram:** просит Telegram username → «мы отправили вам сообщение с кодом в Telegram, подтвердите» → ввод кода → «Authentication successful».

Код всегда `12345` (`SOCIAL_AUTH_MOCK_CODE`), действует 1 минуту, 5 неверных попыток сбрасывают проверку.
**Ничего реально не отправляется:** это имитация, чтобы проверить интерфейс и логику без ключей.
Дальше всё настоящее: создание пользователя, JWT, привязка/отвязка аккаунтов, refresh, logout.
Режим работает **только при `DEBUG=True`**: с выключенным DEBUG бэкенд отклоняет такие запросы
(покрыто тестом).

Google и Facebook с одинаковым email объединяются в одного пользователя, так видно, как работает
связывание аккаунтов. Если нажать кнопку в профиле, провайдер привяжется к текущему аккаунту.

Как только для провайдера задан реальный ключ, его кнопка автоматически работает по-настоящему.

## Как это устроено

### Email и пароль

```
Sign up:  {name, email, password, password_confirm} ─▶ POST /email/signup/  ─▶ письмо с кодом
          {email, code}                             ─▶ POST /email/verify/  ─▶ аккаунт создан (без входа)
Sign in:  {email, password}                         ─▶ POST /login/         ─▶ сессия
Reset:    {email}                                   ─▶ POST /password/reset/          ─▶ письмо с кодом
          {email, code}                             ─▶ POST /password/reset/verify/   ─▶ reset_token
          {token, password, password_confirm}       ─▶ POST /password/reset/confirm/  ─▶ сессия
```

**Пароли**
- Проверяются стандартными валидаторами Django: не короче 8 символов, не из списка частых,
  не только цифры, не похож на имя/email. Хранятся только как хеш (PBKDF2).
- После подтверждения кода вход **не выполняется**: пользователь попадает на `/login` с подставленным
  email и входит паролем (подтверждение заодно проверяет, что пароль запомнен).
- Аккаунт создаётся только после подтверждения email: до этого хеш пароля хранится рядом с кодом.
  Повторная отправка кода (`/email/resend/`) берёт имя и пароль оттуда же, так что фронтенду
  не нужно держать пароль у себя.
- Неверный пароль и несуществующий email дают одинаковый ответ `401 Invalid email or password`
  (и одинаковое время ответа), так что вход не раскрывает, какие email зарегистрированы.
- Rate limit на вход: 10 попыток в минуту с IP.

**Сброс пароля**
- После кода выдаётся подписанный `reset_token`, живущий 10 минут. В нём отпечаток текущего
  хеша пароля, поэтому после смены пароля токен перестаёт работать (одноразовый).
- После смены пароля все прежние сессии завершаются (refresh-токены в blacklist).
- Пользователь, зарегистрированный через соцсеть, может так же задать себе пароль.

**Коды**
- 6 цифр, `secrets`, живут 1 минуту (`EMAIL_CODE_TTL`), одноразовые; в БД хранится только HMAC (код + email).
  Код регистрации нельзя использовать для сброса пароля и наоборот.
- Ввод на отдельной странице `/verify` с обратным отсчётом; после истечения появляется «Resend code».
- 5 неверных попыток → код сгорает; новый код отменяет старый.
- Повторная отправка не чаще раза в 60 с (`429` + `Retry-After`), не больше 5 кодов в час на адрес.
- Регистрация с занятым email → `409 account_exists`, сброс для неизвестного → `404 account_not_found`;
  фронтенд показывает ссылку на нужную страницу.
- Email, сохранённый у пользователя, всегда подтверждён (кодом или провайдером), поэтому
  зарегистрированный по email пользователь, позже вошедший через Google с тем же адресом,
  попадает в тот же аккаунт.

### Соцсети

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
| POST | `/api/auth/login/` | `{email, password}` → сессия |
| POST | `/api/auth/email/signup/` | `{name, email, password, password_confirm}` → отправить код |
| POST | `/api/auth/email/verify/` | `{email, code}` → аккаунт создан; входа нет, дальше `/login/` |
| POST | `/api/auth/email/resend/` | `{email, purpose: "signup"\|"reset"}` → новый код |
| POST | `/api/auth/password/reset/` | `{email}` → отправить код |
| POST | `/api/auth/password/reset/verify/` | `{email, code}` → `{reset_token}` |
| POST | `/api/auth/password/reset/confirm/` | `{token, password, password_confirm}` → сессия |
| POST | `/api/auth/google/` | `{credential}` |
| POST | `/api/auth/facebook/` | `{access_token}` |
| POST | `/api/auth/telegram/` | объект `user` из Telegram widget без изменений |
| POST | `/api/auth/token/refresh/` | refresh из cookie → новый access (refresh ротируется) |
| POST | `/api/auth/logout/` | refresh из cookie → blacklist, cookie удаляется |
| GET/PATCH | `/api/auth/me/` | текущий пользователь |
| DELETE | `/api/auth/social/<provider>/` | отвязать провайдера |
| GET | `/api/auth/providers/` | какие провайдеры настроены |

Ответ на любой вход: `{access, user, created}` (`created: true` = регистрация, HTTP 201),
refresh token приходит только в cookie. Соцсети регистрируют при первом входе и логинят при следующих,
поэтому их кнопки одинаковые на обеих страницах.

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
  отвязать последний способ входа (400). Email считается способом входа: пользователь с email
  может отвязать все соцсети.

**Прочее.** Rate limit на эндпоинты входа (30/мин с IP); пользователь и социальный аккаунт
создаются в одной транзакции; гонка при одновременной привязке обрабатывается через
уникальный индекс.

## Структура

```
backend/
  config/settings.py        настройки, всё секретное — из .env
  accounts/
    providers.py            проверка Google / Facebook / Telegram (+ тестовые профили)
    email_codes.py          email-коды (регистрация, сброс пароля), лимиты
    password_auth.py        вход по паролю, сброс пароля
    services.py             поиск / создание / связывание пользователя, выдача JWT
    cookies.py              httpOnly refresh cookie
    views.py, urls.py       API
    models.py               SocialAccount, EmailCode
    tests.py                тесты
frontend/src/
  api/client.ts             axios: access token, авто-refresh при 401
  auth/                     AuthContext, хранение access token в памяти
  components/               кнопки провайдеров, форма email, ввод кода
  pages/                    Sign in, Sign up, Verify, Forgot/Reset password, Connect, профиль
  types.ts                  типы API
```

## Проверки

```bash
# backend
venv\Scripts\python manage.py test accounts   # 63 теста
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
- SMTP для писем (`EMAIL_HOST` и т.д.).
- PostgreSQL вместо SQLite.
