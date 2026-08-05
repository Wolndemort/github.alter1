# ALTER

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
- 120 локальных тестов.

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

## Переменные `.env`

```env
BOT_TOKEN=...
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=google/gemini-2.5-flash
OPENROUTER_FALLBACK_MODEL=openai/gpt-4o-mini
OPENROUTER_FALLBACK_MODEL_2=anthropic/claude-3.5-haiku
YOUTUBE_API_KEY=...
TAVILY_API_KEY=...
TRANSCRIPTION_MODEL=openai/whisper-1
TTS_MODEL=openai/gpt-audio-mini
TTS_VOICE=alloy
DATABASE_URL=...
SESSION_TIMEOUT=300
DAILY_REQUEST_LIMIT=100
```

Текущая рабочая связка: Gemini 2.5 Flash как основная модель, затем GPT-4o-mini и Claude 3.5 Haiku как fallback через OpenRouter. После изменения моделей достаточно пересоздать контейнер bot:

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

Обычный текстовый и медиа-поиск проходит через `generate_reply`/`generate_media_reply` и planner/executor tool loop. Regex-интенты больше не решают, искать ли web-факты или погоду. Audio action тоже проходит через semantic-планировщик; число раундов задаётся `TOOL_MAX_ROUNDS` (по умолчанию 6, максимум 12). Каждый результат получает статус `ok`, `empty` или `error`; при проблеме planner может один раз изменить стратегию без участия пользователя.

После генерации `utils/quality.py` выполняет быстрый quality gate: проверяет пустоту, чрезмерную длину, лишние вопросы, утечку служебных полей и атрибуцию переданных источников. Ответ не блокируется, а предупреждение попадает в метрики. Это дешёвый runtime-контроль; глубокая фактологическая оценка выполняется отдельными eval-тестами.

## Итог текущей итерации

ALTER сейчас состоит не только из chat-вызова. В рабочем потоке есть память, семантический planner/executor, разрешённые инструменты, fallback-модели, проверка результата инструментов, quality gate, метрики, preflight зависимостей и offline smoke/eval-тесты.

Текущий локальный baseline: `120 passed`, `compileall` проходит. Для локальной проверки Docker не нужен: `py -m pytest -q`, `py -m compileall -q .`, затем `py main.py`. Реальные Redis/PostgreSQL и Telegram нужны только для серверного интеграционного запуска.
