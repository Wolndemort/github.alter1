# ALTER

Полная инструкция по API, маршрутам и текстовым/голосовым командам: [docs/USER_API_GUIDE.md](docs/USER_API_GUIDE.md).

## Актуальный production baseline (2026-08-08)

- Backend: 249 тестов проходят локально; mobile TypeScript и тесты проходят.
- Тарифы: ALTER Personal — 990 ₽/30 дней; ALTER Ego — 2990 ₽/30 дней.
- Квоты: Personal — 1000 кредитов/месяц, Ego — 3500 кредитов/месяц. Telegram и мобильное приложение используют общий Redis-счётчик.
- YooKassa: карта и СБП, проверка суммы/status/metadata, idempotency, webhook и автопродление.
- Production smoke: `scripts/production-smoke.sh`; readiness: `/health` и `/ready`.
- `gym_nginx` владеет 80/443 и проксирует ALTER через `web_network`; ALTER host-порты не публикует.
- Expo Go + Metro подходят для базовой локальной проверки. Development Build нужен для нативных модулей и push; Apple Developer Program нужен отдельно для TestFlight/App Store.

Квоты и расчёт себестоимости находятся в [QUOTAS_AND_UNIT_ECONOMICS.md](QUOTAS_AND_UNIT_ECONOMICS.md).

## UX and usage baseline

Mobile and Telegram share the same session rule: starting a new chat closes the active session and persists its summary; clearing memory is explicit and is never performed by starting a new chat. Metro only serves JavaScript locally; the mobile `.env` points to the production API.

The mobile profile uses collapsible groups (profile, connections, tools, application). Email is masked and revealed only on tap. Voice replies and automatic playback are independent settings. Assistant answers expose copy, manual playback, and feedback actions.

Monthly usage is stored in Redis and shared by API and Telegram. Current costs are: text 1 credit, voice 5, media analysis 20, media generation 40, and ElevenLabs audio actions 20. `/api/v1/usage` returns used, limit, and remaining credits. Plans are quota-based; unlimited external-provider operations are not promised. Audio actions are requested naturally: “создай звук дождя”, or attach a voice and say “наложи звук дождя на моё голосовое” / “почисти запись от шума”.

Parity checks: `/new_session` and the mobile New Chat action persist summaries; `/clear_memory` removes only durable memory; Telegram media actions restore the latest media from the session, so Improve Photo does not depend on the reply message containing a photo.

## Current project state (2026-08-06)

### Latest implementation notes (2026-08-07)

- The mobile app uses a dark premium UI with a one-time-per-session permission card. It explains why notifications and location improve ALTER, then requests system permissions only after the user presses the allow button. “Later” dismisses the card for the current session.
- Registration includes an explicit legal consent checkbox with links to the privacy policy and offer. Native blue buttons were replaced with the ALTER visual style.
- Push tokens are validated and stored in the existing user settings JSON. Location is sent with chat only after consent; precise coordinates are not persisted as a separate database record.
- Telegram media messages show human-readable actions: analyze, improve photo, and animate video. The photo action calls the shared generation pipeline; video remains an asynchronous provider flow and must never claim success before a file exists.
- fal.ai configuration uses `MEDIA_PROVIDER=fal`, `FAL_BASE_URL=https://fal.run`, `fal-ai/flux-pro/kontext/max` for image editing, and `fal-ai/kling-video/v2.1/master/image-to-video` for video. Keep the API key only in `.env` on the server.
- The Telegram/app identity merge avoids lazy SQLAlchemy relationship IO; notification monitors never send an app database id as a Telegram chat id.

Latest verification baseline: `249` backend tests, mobile tests, mobile TypeScript check, Python compilation, and `git diff --check` pass. Expo Go push limitations are expected; production remote push requires a development build/TestFlight.

### Metro / Expo quick start

From `mobile`:

```powershell
npx expo start --offline --port 8082 -c
```

Do not combine Expo `--offline` with `--lan`; Expo treats them as mutually exclusive. In offline mode Metro still serves the local bundle on port `8082`. If a QR is needed, run the command in a visible terminal. For the current LAN address the Expo Go URL is usually `exp://<computer-lan-ip>:8082`.

### VPS update

```bash
cd /root/alter
git pull --ff-only origin master
docker compose up -d --build bot alter-nginx
docker compose logs --since=2m --tail=100 bot
```

ALTER has an independent Expo mobile client alongside the existing Telegram
client. Both clients use the same users, memory, sessions, reminders,
subscriptions, and payments. No duplicate mobile database was introduced.

### Local iPhone testing

Use this mode while the iPhone and computer are on the same Wi-Fi network:

```powershell
cd C:\Users\79615\PycharmProjects\Alter\mobile
npm install --registry=https://registry.npmmirror.com --fetch-timeout=120000 --fetch-retries=5
npx expo start --offline --port 8082 -c
```

Scan the QR code in Expo Go. Press `r` in Metro to reload. `--offline` only
disables Expo registry checks; the app still uses the HTTPS API from
`mobile/.env`.

Same-network mode without the offline flag:

```powershell
npx expo start --lan --port 8082 -c
```

Mobile-network testing through Expo Go needs a tunnel. ngrok is currently
unstable, so this is temporary:

```powershell
npx expo start --tunnel --port 8082
```

Permanent iPhone use without a computer requires EAS/TestFlight and an Apple
Developer Program account. Telegram remains available remotely meanwhile.

### Verification commands

```powershell
cd C:\Users\79615\PycharmProjects\Alter
py -3 -m pytest -q
py -3 -m compileall -q .
git diff --check
cd mobile
cmd /c "npx tsc --noEmit"
cmd /c "npm test -- --runInBand"
```

Verified current result: `236` backend tests and `11` mobile tests pass.
TypeScript passes too. The SafeAreaView output is only a deprecation warning.

### Completed mobile work

- Expo SDK 54 dependency alignment and lockfile update.
- Black/white futuristic interface with a violet accent and animated intro.
- Optional intro sound through `EXPO_PUBLIC_INTRO_SOUND_URL`.
- Email registration, six-digit verification, resend, and token persistence.
- Chat typing animation, keyboard insets, automatic scroll-to-bottom, media
  picker, multipart image/video upload, and press-and-hold violet microphone.
- Minimal account cabinet with white ALTER-style typography, memory screen,
  subscription/payment action, logout, and `Synchronize memory with Telegram`.
- AppState foreground recovery after returning from background.
- Readable network timeouts and clickable HTTPS links in assistant replies.
- Separate card controls for auto-renewal and removing the saved payment method.
- Explicit foreground geolocation choice with optional iOS background permission;
  an approved city/coordinate context is sent only with chat requests and is
  not persisted as a precise location in the database.
- Expo push permission/token registration; production remote push requires a
  development build or TestFlight, while Expo Go is suitable for basic tests.

### Completed backend work

- Auth endpoints: register, verify email, resend code, login, and account.
- Shared chat, memory, media, weather/tools, reminders, settings, YouTube,
  subscriptions, YooKassa payments, and Telegram-link APIs.
- One-time Redis Telegram link merges mobile and Telegram profiles.
- SMTP and console email modes; console mode is useful for testing only.
- `OWNER_TELEGRAM_IDS` and `OWNER_EMAILS` bypass subscription checks for the
  owner without adding a database field or migration.
- `POST /api/v1/push-token` stores an Expo token in the existing `tech_stack`
  JSON. Reminder and check-in monitors send to Telegram and mobile push.
- `PATCH /api/v1/subscription/auto-renew` toggles recurring charges.
- `DELETE /api/v1/subscription/payment-method` disables recurring charges and
  removes the saved payment method reference.
- YooKassa card saving is opt-in through `YUKASSA_SAVE_PAYMENT_METHOD=false`.

### VPS update after a push

The `.env` file is never committed. On the server:

```bash
cd /root/alter
git pull --ff-only origin master
```

Ensure the server `.env` contains:

```dotenv
OWNER_EMAILS=kid.cudi.1995@mail.ru
OPENROUTER_ALLOW_PAID_FALLBACK=true
YUKASSA_SAVE_PAYMENT_METHOD=false
```

Rebuild and verify:

```bash
docker compose run --rm migrations
docker compose up -d --build bot alter-nginx
docker compose ps
curl https://api.alterai.ru/health
docker compose logs --tail=120 bot
```

Expected health response: `{"ok":true}`.

### OpenRouter key diagnostic

The OpenRouter key has its own spending limit. A key with
`limit_remaining: 0` returns `403` even after account top-up. Check it without
printing the key:

```bash
cd /root/alter
docker compose exec bot python -c "from config import config; import httpx; r=httpx.get('https://openrouter.ai/api/v1/key',headers={'Authorization':'Bearer '+config.OPENROUTER_API_KEY.get_secret_value()}); print(r.status_code, r.text)"
```

Never paste API keys or passwords into chat, Git, README, or screenshots.

### Important files

Recent implementation notes are kept in [PROJECT_MAP_ADAM_RECENT.md](PROJECT_MAP_ADAM_RECENT.md).

| Area | Files |
|---|---|
| Mobile UI | `mobile/App.tsx` |
| Mobile API/tests | `mobile/src/api/client.ts`, `mobile/App.test.tsx`, `mobile/src/api/client.test.ts` |
| Auth/email | `api/auth_routes.py`, `services/auth_service.py`, `services/email_service.py` |
| Chat/media | `api/chat_routes.py`, `api/youtube_routes.py`, `services/chat_service.py` |
| Billing/access | `utils/billing.py`, `config.py` |
| Migrations | `alembic/versions/0016_email_verification.py`, `0017_telegram_account_link.py` |
| API contract | `docs/APP_API.md` |

Telegram-ассистент на aiogram с памятью, живым диалогом, голосовыми, фото, видео, музыкой, погодой, напоминаниями и check-in.

## Возможности

### Живое поведение

ALTER не ограничивается ответом на последний вопрос. После завершения неактивной сессии он:

- сохраняет явно сообщённые факты в долговременную память;
- выделяет важные события и незавершённые темы (`open_loops`);
- может позже мягко вернуться к такой теме;
- иногда сам задаёт один уместный вопрос через check-in.

Инициативность ограничена настройками check-in и не должна превращать диалог в анкету. Факты не выдумываются, а память можно посмотреть или очистить командами ниже.

- текстовый диалог через OpenRouter;
- краткосрочная история и долговременная JSONB-память;
- голосовые: расшифровка используется внутри ALTER, текст расшифровки пользователю не отправляется;
- анализ фото и коротких видео;
- поиск музыки и видео через YouTube;
- отправка найденной песни как MP3 в Telegram с кнопкой Play;
- веб-поиск через Tavily: люди, новости, цены, погода, рекомендации и актуальные события;
- поиск товаров в Wildberries и Ozon;
- погода через `/weather Москва` или фразу «погода в Москве»;
- напоминания, follow-up и мягкие check-in;
- PostgreSQL, Redis, Docker Compose и Alembic;
- 121 локальный тест.

## Запуск

1. Создайте `.env` по примеру переменных ниже.
2. Запустите Docker Desktop.
3. Выполните:

```powershell
docker compose up -d --build
docker compose logs -f bot
```

После изменения миграций:

```powershell
docker compose run --rm --build migrations alembic upgrade head
```

## Проверки

```powershell
.\venv\Scripts\python.exe -m compileall -q .
.\venv\Scripts\python.exe -m pytest -q
docker compose config --quiet
```

Без запуска Docker можно проверить весь offline-контур:

```powershell
py -m pytest -q
py -m compileall -q .
py main.py
```

Последняя команда при недоступных Redis/PostgreSQL завершится безопасно после preflight и напечатает причину, не зависая на polling.

## Метрики и диагностика

ALTER пишет метрики в обычный лог приложения. Это не содержит токенов, ключей или текста пользовательских сообщений.

Основные имена:

- `ai.model.success` / `ai.model.failure` — доступность моделей и fallback;
- `ai.reply.success` / `ai.reply.failure` — итог генерации ответа;
- `search.web.success` / `search.web.failure` — Tavily;
- `memory.vector.recall_success`, `memory.vector.recall_failure`, `memory.vector.save_failure` — векторная память;
- `voice.transcription.success` / `voice.transcription.failure` — Whisper;
- `voice.tts.success`, `voice.tts.empty`, `voice.tts.failure` — голосовой ответ;
- `ai.tool.ok`, `ai.tool.empty`, `ai.tool.error`, `ai.tool.failure`, `ai.tool.round_limit` — planner/executor и проверка результата;
- `ai.reply.quality`, `ai.reply.quality_warning` — автоматический quality gate финального ответа;
- `metric=<name> duration=...` — длительность операций.

На сервере смотреть поток:

```bash
docker compose logs -f --tail=200 bot | grep --line-buffered 'metric'
```

Для краткой диагностики последних ошибок:

```bash
docker compose logs --since=1h bot | grep -E 'metric_count=.*failure|ERROR|Traceback'
```

В Windows без Docker метрики видны в выводе `py main.py`; счётчики живут в памяти процесса и сбрасываются после перезапуска. Для долгосрочных графиков следующим этапом можно подключить Prometheus/Loki, но для текущей отладки grep-friendly логов достаточно.

## Резервная копия базы — обязательно

Перед крупными изменениями и после первого запуска создайте копию:

```powershell
.\scripts\backup-db.ps1
```

Файл появится в `backups/`. Эта папка исключена из Git.

### Ежедневный backup в Windows

Откройте «Планировщик заданий» → «Создать простую задачу»:

- имя: `ALTER database backup`;
- расписание: ежедневно, например 04:00;
- действие: запуск программы `powershell.exe`;
- аргументы: `-ExecutionPolicy Bypass -File "C:\Users\79615\PycharmProjects\Alter\scripts\backup-db.ps1"`;
- рабочая папка: `C:\Users\79615\PycharmProjects\Alter`.

Docker Desktop и контейнер PostgreSQL должны быть запущены. Старые копии периодически переносите на другой диск или в облако.

### Ежедневный backup на Linux/VPS

Скрипт для VPS создаёт проверенный custom-дамп PostgreSQL вместе с pgvector и удаляет копии старше 14 дней:

```bash
chmod +x scripts/backup-db.sh
./scripts/backup-db.sh
ls -lh backups/
```

Добавьте ежедневный запуск в cron:

```cron
0 4 * * * cd /root/alter && /bin/bash ./scripts/backup-db-to-s3.sh >> /var/log/alter-backup.log 2>&1
```

Файл считается успешным только после проверки `pg_restore --list`. Рекомендуется регулярно копировать папку `backups/` на другой диск или в облако: backup на том же сервере не защищает от потери VPS.

После ручного запуска в `backups/` должен появиться файл `alter-YYYYMMDD-HHMMSS.dump` ненулевого размера. Если папка пустая, запустите диагностику:

```bash
cd /root/alter
bash -x ./scripts/backup-db.sh
docker compose exec -T db pg_dump --version
docker compose ps
tail -n 100 /var/log/alter-backup.log
```

Не считайте cron настроенным, пока ручной запуск не создал проверенный `.dump`. После настройки проверьте расписание командой `crontab -l`.

### Yandex Object Storage

После привязки платёжного аккаунта создайте бакет в Object Storage. На VPS установите AWS CLI и создайте `/root/alter/.backup.env` с правами `600`:

```env
S3_BUCKET=имя-бакета
AWS_ACCESS_KEY_ID=идентификатор_static_access_key
AWS_SECRET_ACCESS_KEY=секрет_static_access_key
S3_PREFIX=postgres
# Optional; defaults to 90 days.
CLOUD_RETENTION_DAYS=90
```

Проверьте вручную:

```bash
chmod 600 /root/alter/.backup.env
chmod +x /root/alter/scripts/backup-db-to-s3.sh
/root/alter/scripts/backup-db-to-s3.sh
```

Скрипт сначала создаёт и проверяет PostgreSQL custom dump, затем загружает его в Yandex Object Storage и проверяет объект через `head-object`. Секреты не добавляйте в Git.

Локальные копии на VPS хранятся в `/root/alter/backups/` 14 дней. Облачные копии в `s3://<bucket>/postgres/` хранятся минимум 90 дней; `scripts/backup-db-to-s3.sh` удаляет только объекты старше `CLOUD_RETENTION_DAYS`.

Проверка облачного backup:

```bash
aws s3 ls s3://alter-postgres-backups-79615/postgres/ \
  --endpoint-url https://storage.yandexcloud.net
tail -n 100 /var/log/alter-backup.log
```

На VPS должна быть только одна cron-запись:

```cron
0 4 * * * cd /root/alter && /bin/bash ./scripts/backup-db-to-s3.sh >> /var/log/alter-backup.log 2>&1
```

Восстановление всегда сначала проверяйте на отдельной тестовой базе; не восстанавливайте dump поверх рабочей базы без отдельного backup.

## Архитектура памяти

ALTER разделяет память на несколько уровней:

- текущий диалог — только последние сообщения, чтобы не раздувать prompt;
- структурированная память `users.memory` — стабильные факты, цели и незавершённые темы;
- векторная память `memory_chunks` — эпизоды, найденные по смыслу;
- `important_events` и `reminders` — события и действия, к которым нужно вернуться.

Векторный поиск не добавляет в prompt любые ближайшие записи. Он ограничен пользователем, числом результатов и порогом cosine distance. Для содержательных сообщений включается автоматический поиск, а короткий small talk не тратит запрос на embeddings. Если похожих фрагментов нет, память в ответ не подмешивается.

Память и история дополнительно ограничиваются перед запросом к модели. Это важно для бесплатных моделей OpenRouter с небольшим context window: долговременные данные сохраняются в БД, но в конкретный prompt попадают только нужные фрагменты.

Vector memory дополнительно защищена от повторной записи через `content_hash`, имеет `importance` и срок хранения `expires_at`. Истёкшие фрагменты удаляются отдельной ежедневной cleanup-задачей, а для PostgreSQL/pgvector создаётся HNSW cosine-индекс миграцией `0014_memory_lifecycle`.

Настройки memory:

```env
MEMORY_RECALL_LIMIT=3
MEMORY_RECALL_MAX_DISTANCE=0.35
MEMORY_AUTO_RECALL_MIN_CHARS=40
MEMORY_PROMPT_MAX_CHARS=4500
MEMORY_SUMMARY_MAX_CHARS=7000
```

## Переменные `.env`

```env
BOT_TOKEN=...
OPENROUTER_API_KEY=...
OPENROUTER_FREE_MODEL=google/gemma-4-31b-it:free
OPENROUTER_FREE_MODEL_2=inclusionai/ling-3.0-flash:free
OPENROUTER_FREE_MODEL_3=nvidia/nemotron-3-super-120b-a12b:free
OPENROUTER_FREE_MODEL_4=google/gemma-4-26b-a4b-it:free
OPENROUTER_FREE_MODEL_5=openai/gpt-oss-20b:free
OPENROUTER_MODEL=openai/gpt-5.6-luna
OPENROUTER_FREE_VISION_MODEL=google/gemma-4-31b-it:free
OPENROUTER_FREE_VISION_MODEL_2=nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free
OPENROUTER_REASONING_MODEL=inclusionai/ling-2.6-1t
OPENROUTER_FALLBACK_MODEL=inclusionai/ling-2.6-flash
OPENROUTER_FALLBACK_MODEL_2=openai/gpt-5.6-terra
OPENROUTER_ALLOW_PAID_FALLBACK=true
OWNER_TELEGRAM_IDS=1271717628
SUPPORT_USERNAME=Adam_Omarov
SUPPORT_TELEGRAM_ID=1271717628
LEGAL_BASE_URL=https://alterai.ru
YUKASSA_SHOP_ID=...
YUKASSA_SECRET_KEY=...
YUKASSA_RECEIPT_EMAIL=...
SUBSCRIPTION_PRICE_RUB=490.00
SUBSCRIPTION_DAYS=30
SUBSCRIPTION_RENEWAL_CHECK_SECONDS=3600
YOUTUBE_API_KEY=...
TAVILY_API_KEY=...
TRANSCRIPTION_MODEL=openai/whisper-1
TTS_MODEL=openai/gpt-audio-mini
TTS_VOICE=alloy
DATABASE_URL=...
SESSION_TIMEOUT=300
DAILY_REQUEST_LIMIT=100
```

Текущая рабочая связка: бесплатные модели OpenRouter идут первыми, затем `openai/gpt-5.6-luna`, reasoning-модель `inclusionai/ling-2.6-1t` и платные fallback-модели. После изменения моделей достаточно пересоздать контейнер bot:

```powershell
docker compose up -d --no-deps --force-recreate bot
```

Пересборка с `--build` нужна только после изменений кода или Dockerfile.

### YouTube: ссылки или аудио

Для обычных ссылок и превью используй формулировки:

```text
Найди на YouTube Tool Sober
Пришли ссылку на песню Tool Sober
Покажи видео Tool Sober на YouTube
Найди клип Nirvana
```

Для отправки аудиофайла прямо в Telegram:

```text
Включи песню Tool Sober
Пришли песню Nirvana — Come As You Are
Скачай песню Tool Sober
```

В аудиорежиме бот скачивает первый найденный результат через `yt-dlp`, конвертирует его в MP3 192 kbps с помощью `ffmpeg` и отправляет Telegram-аудио с кнопкой Play. Временный файл удаляется после отправки. Список YouTube-ссылок после успешно отправленного аудио не дублируется.

Для аудиорежима контейнер должен быть пересобран после обновления кода:

```bash
docker compose up -d --build bot
docker compose exec -T bot yt-dlp --version
docker compose exec -T bot ffmpeg -version | head -n 1
```

Используй скачивание только для контента, который разрешено скачивать и распространять.

### Веб-поиск

Tavily используется как отдельный поисковый слой. Модель не открывает интернет самостоятельно: бот сначала отправляет запрос в Tavily, затем передаёт найденные заголовки, выдержки и ссылки основной модели. Если Gemini не отвечает, тот же контекст получают GPT и Claude по цепочке fallback.

Поиск включается для естественных запросов вроде «найди», «кто такой», «расскажи про», «что известно о», «новости», «цена», «погода», «биография» и «посоветуй». В ответе выводятся источники. Для YouTube используется отдельный YouTube API.

На сервере добавьте ключ в `.env` и пересоздайте контейнер:

```bash
TAVILY_API_KEY=...
docker compose up -d --build bot
docker compose logs -f --tail=100 bot
```

Если ключ не найден, в логах появится `TAVILY_API_KEY is not configured`. Сам запрос Tavily выполняется через `aiohttp`, поэтому в стандартном логе может не быть строки `httpx`; ориентируйтесь на блок `🌐 Источники` в ответе.

Никогда не публикуйте `.env`, токен Telegram или API-ключи. Если ключ попал в чат или Git, его нужно заменить.

## Подписка, биллинг и юридические документы

ALTER использует YooKassa для доступа на 30 дней. Поддерживаются оплата банковской картой и СБП. После оплаты бот проверяет платёж через API YooKassa и активирует подписку только после проверки статуса, суммы, валюты и metadata платежа.

Первая оплата картой может сохранить платёжный метод для автопродления. Автопродление выключено по умолчанию и включается пользователем в кабинете. СБП является разовой оплатой и не используется для автосписаний. Фоновая задача проверяет продления каждый час, а отдельный планировщик отправляет напоминания за 5, 3 и 1 день до окончания подписки. Повторные уведомления защищены маркерами в PostgreSQL.

Новые пользователи при первом `/start` видят и принимают четыре документа: `legal/privacy.html`, `legal/consent.html`, `legal/offer.html` и `legal/refund.html`. До принятия согласия middleware не пропускает обычные сообщения и оплату. Страницы нужно опубликовать на домене из `LEGAL_BASE_URL` до публичного запуска.

После создания платежа пользователь возвращается в Telegram по deep-link `start=payment_<idempotence_key>`. Дополнительно ALTER принимает подтверждения YooKassa через `POST /webhooks/yookassa`; webhook не доверяет входному JSON для активации, а повторно проверяет платёж через API YooKassa.

Для YooKassa укажи URL уведомлений:

```text
https://api.alterai.ru/webhooks/yookassa
```

В событиях включи как минимум `payment.succeeded` и `payment.canceled`. Nginx проксирует endpoint во внутренний порт bot `8080`. Проверка доступности: `https://api.alterai.ru/health`.

Фоновые задачи используют транзакционные блокировки PostgreSQL (`FOR UPDATE SKIP LOCKED`) для сессий, check-in, expiry-напоминаний, renewals и обычных reminders. Это предотвращает двойную обработку при случайном запуске второго экземпляра.

Обычная оплата картой сохраняет `payment_method_id`, а СБП оплачивает подписку без сохранения метода и поэтому не включает рекуррент автоматически. Автопродление включается отдельной кнопкой в кабинете только после успешной оплаты картой.

## Команды

- `/help` — справка;
- `/weather Москва` — погода;
- `/memory` — показать память;
- `/forget skills_career` — удалить категорию памяти;
- `/clear_memory` — очистить долговременную память;
- `/new_session` — начать новый разговор;
- `/remind 2026-08-04 10:00 текст` — создать напоминание;
- `/reminders` — список напоминаний;
- `/cancel_reminder ID` — отменить напоминание;
- `/checkins_on`, `/checkins_off` — включить или выключить check-in.
- `/buy` — открыть оплату подписки картой или через СБП;
- `/status` — проверить подписку и обновить статус последнего платежа;
- `/settings` — показать настройки поведения ALTER;
- `/checkin_every 24` — частота обычных check-in в часах;
- `/health_followup 4` — задержка проверки самочувствия;
- `/quiet_hours 23 8` — тихие часы для фоновых сообщений.
- `/memory` — также позволяет проверить сохранённые важные события и незавершённые темы.

## Структура

- `main.py` — запуск бота и фоновых задач;
- `handlers/` — Telegram-команды и сообщения;
- `middleware/` — база данных и лимиты;
- `utils/ap_logic.py` — ответы AI и память;
- `utils/metrics.py` — счётчики, тайминги и диагностические события;
- `utils/billing.py` — YooKassa, подписки, СБП и автопродление;
- `utils/tasks.py` — фоновые задачи памяти, напоминаний, продлений и уведомлений об окончании подписки;
- `utils/runtime.py` — offline-safe preflight Redis/PostgreSQL;
- `utils/quality.py` — автоматическая проверка качества ответа;
- `utils/media_logic.py` — анализ изображений;
- `utils/media.py` — кадры и аудио из видео через ffmpeg;
- `utils/voice.py` — speech-to-text;
- `utils/weather.py` — погода;
- `utils/youtube_search.py` — музыка и YouTube;
- `utils/audio_search.py` — скачивание и отправка аудио через `yt-dlp` и `ffmpeg`;
- `data/models.py` — модели PostgreSQL;
- `alembic/` — миграции;
- `legal/` — политика конфиденциальности, согласие, оферта и правила возврата;
- `scripts/backup-db.ps1` — резервная копия;
- `scripts/backup-db.sh` — автоматический проверенный backup PostgreSQL для Linux/VPS;
- `tests/` — тесты.

## План развития «умного» ALTER

1. Надёжность: fallback-модели, безопасные инструменты, preflight и offline smoke-тесты.
2. Память: разделять факты, события, незавершённые дела и семантически похожий контекст; всегда уважать исправления и команды удаления.
3. Маршрутизация: быстрый режим для простых сообщений, reasoning-модель для планов, сравнений, кода и дебага.
4. Инструменты: поиск, погода и YouTube выбираются planner’ом по смыслу запроса, а не по захардкоженным фразам; результат проверяется и объясняется со ссылками.
5. Контекст: ограничивать prompt, не повторять память дословно, сохранять нить диалога между текстом, голосом и медиа.
6. Проактивность: возвращаться к `open_loops` аккуратно, с quiet hours, лимитами и без ощущения анкеты.
7. Наблюдаемость и качество: метрики, сценарные eval-тесты и регулярная проверка реальными диалогами.

Eval-сценарии находятся в `tests/test_smart_eval.py`. Они проверяют нормализацию и исправление памяти, `open_loops`, границы web-intent, выбор reasoning-модели и allow-list инструментов. Запуск:

```powershell
py -m pytest -q tests/test_smart_eval.py
```

Обычный текстовый и медиа-поиск проходит через `generate_reply`/`generate_media_reply` и planner/executor tool loop. Regex-интенты больше не решают, искать ли web-факты или погоду. Audio action тоже проходит через semantic-планировщик; число раундов задаётся `TOOL_MAX_ROUNDS` (текущее значение по умолчанию — 2). Каждый результат получает статус `ok`, `empty` или `error`; при проблеме planner может один раз изменить стратегию без участия пользователя.

После генерации `utils/quality.py` выполняет быстрый quality gate: проверяет пустоту, чрезмерную длину, лишние вопросы, утечку служебных полей и атрибуцию переданных источников. Ответ не блокируется, а предупреждение попадает в метрики. Это дешёвый runtime-контроль; глубокая фактологическая оценка выполняется отдельными eval-тестами.

## Итог текущей итерации

После добавления биллинга, legal consent, webhook и memory lifecycle полный локальный suite проверяется CI; `compileall` проходит.

ALTER сейчас состоит не только из chat-вызова. В рабочем потоке есть память, семантический planner/executor, разрешённые инструменты, fallback-модели, проверка результата инструментов, quality gate, метрики, preflight зависимостей и offline smoke/eval-тесты.

Текущий локальный baseline меняется вместе с тестовым suite. Для локальной проверки Docker не нужен: `py -m pytest -q`, `py -m compileall -q .`, затем `py main.py`. Реальные Redis/PostgreSQL и Telegram нужны только для серверного интеграционного запуска.
