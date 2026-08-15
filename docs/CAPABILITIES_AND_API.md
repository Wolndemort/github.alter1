# ALTER: возможности, API и сценарии

Единая карта возможностей ALTER для web, mobile и Telegram. Все три клиента используют общий backend, сессии, память и Redis-квоты. Канонический machine-readable источник — `GET /api/v1/capabilities` (каталог версии `2026-08-15`).

## Готово

| Возможность | Backend | Mobile | Telegram | Провайдер |
|---|---|---|---|---|
| Чат | POST /api/v1/chat/messages | Да | Да | OpenRouter |
| Память | GET /api/v1/memory, DELETE /api/v1/memory/{category}, DELETE /api/v1/memory | Да | /memory, /forget и /clear_memory | PostgreSQL/pgvector |
| Новый чат | POST /api/v1/chat/new | Да | /new_session | PostgreSQL |
| Голос в текст | POST /api/v1/chat/media | Да | голосовое | Whisper/OpenRouter |
| Текст в голос | POST /api/v1/voice/reply | Да | /voice | ElevenLabs + fallback OpenRouter |
| Фото и видео | POST /api/v1/chat/media | Да | Да | OpenRouter vision |
| Генерация media | POST /api/v1/media/generate | Да | media actions | Fal.ai |
| Web-поиск | tool web_search | Через чат | Через чат | Tavily |
| YouTube | POST /api/v1/youtube/search и audio | API | Через чат | YouTube + yt-dlp |
| Напоминания | api/v1/reminders | Да | /reminders | PostgreSQL + push |
| Push | POST /api/v1/push-token | Да | — | Expo Notifications |
| Геолокация | location в chat payload | С согласием | — | Expo Location |
| Создание звука | POST /api/v1/audio/sound-effects или обычная фраза | Да | Да | ElevenLabs Sound Effects |
| Очистка голоса | endpoint сохранён для совместимости | Нет | Нет | Недоступно с текущим ключом ElevenLabs (401) |
| Наложение звука | аудиовложение + естественная команда | Да | Да | ElevenLabs + ffmpeg |

## Примеры для пользователя

- «Запомни, что я изучаю Python».
- «Напомни завтра в 10:00 позвонить маме».
- «Найди актуальную цену iPhone».
- «Посмотри это фото и скажи, что улучшить».
- «Измени это фото в кинематографичном стиле».
- «Оживи это изображение».
- «Найди песню и пришли аудио».
- «Озвучь последний ответ».
- «Включи голосовые ответы» или «Озвучивай ответы автоматически».
- «Создай звук дождя по стеклу» — ALTER вернёт готовый звуковой эффект.
- Прикрепи голосовое и напиши или скажи: «Наложи звук дождя на моё голосовое».
- Прикрепи голосовое и напиши: «Почисти запись от шума» — вернётся очищенный mp3.

## ElevenLabs

В .env используются ELEVENLABS_ENABLED=true, ELEVENLABS_MODEL=eleven_multilingual_v2 и ELEVENLABS_VOICE_ID. Для Premium voice настройка пользователя должна содержать tts_voice=elevenlabs. При сбое или отсутствии баланса backend использует OpenRouter fallback.

Sound Effects, TTS, STT, speech-to-speech, voice generation, voices, models и audio mix доступны через текущие маршруты. Audio Isolation не рекламируется как доступная возможность: endpoint сохранён для совместимости, но текущий ключ ElevenLabs отвечает `401`.

## Fal.ai

Fal используется для генерации и изменения изображений/видео. Настройки: MEDIA_PROVIDER=fal, MEDIA_GENERATION_API_KEY, FAL_IMAGE_MODEL, FAL_VIDEO_MODEL. Запросы проходят через POST /api/v1/media/generate; результат считается успешным только после получения готового файла.

## Экономика

- текст — 1 кредит;
- голосовой ответ — 5 кредитов;
- media analysis — 20 кредитов;
- media generation — 40 кредитов;
- YouTube search/audio — отдельные кредиты;
- Sound Effects и audio mix — 20 кредитов за операцию;
- Personal — 1000 кредитов;
- Ego — 3500 кредитов.

Владелец получает доступ без подписки, но внешние провайдеры сохраняют собственные лимиты и стоимость.

## Правило parity

Новую возможность сначала добавляем в service/API слой, затем подключаем к mobile и Telegram. Для каждого нового внешнего API обязательны auth, owner/subscription check, quota charge, timeout, обработка ошибок, fallback где уместно и contract tests.

## Текущие routes ElevenLabs

- audio effects — Sound Effects;
- speech-to-speech / voice generation;
- speech-to-text, text-to-speech, voices и models;
- audio mix через `POST /api/v1/audio/process`.

`POST /api/v1/audio/isolate` оставлен только как compatibility route и должен
возвращать контролируемую ошибку недоступности, а не считаться успешной
возможностью.
## Web-поиск: Tavily + Firecrawl

Web-поиск вызывается обычной фразой в Telegram или mobile: «найди актуальную цену», «проверь новость по нескольким сайтам», «изучи страницу и дай ссылки». Называть провайдера не требуется.

Tavily выполняет углублённый поиск, Firecrawl дополнительно извлекает содержимое страниц. Backend объединяет ответы, удаляет одинаковые URL и использует оставшийся провайдер при временном отказе второго.

```env
TAVILY_API_KEY=...
FIRECRAWL_API_KEY=...
FIRECRAWL_SEARCH_LIMIT=10
```

`FIRECRAWL_SEARCH_LIMIT` — число результатов на один запрос, а не месячная квота. Внешняя квота Firecrawl принадлежит API-ключу и действует также для owner. Owner получает бесплатный доступ только в рамках внутренних кредитов ALTER; внешние ограничения провайдера не обходятся.
## Google Calendar

Подключение выполняется через OAuth Google. Для backend используется redirect URI `https://api.alterai.ru/api/v1/calendar/oauth/callback`. Доступные маршруты: `/api/v1/calendar/connect`, `/api/v1/calendar/status`, `/api/v1/calendar/calendars`, `/api/v1/calendar/events` и `/api/v1/calendar/oauth/callback`.

В Telegram: `/calendar_connect`, `/calendar`, `/calendar_add YYYY-MM-DD HH:MM YYYY-MM-DD HH:MM название`. После OAuth те же действия доступны mobile через общий API.
Календарь понимает одинаковые текстовые и голосовые обращения: «подключи Google Calendar», «покажи события», «добавь встречу завтра в 10:00», «удали событие event-123». Голосовой input сначала проходит Speech-to-Text.
## Мультимодальный контур и vision roadmap

ALTER принимает текст, голос, изображения, видео и документы. Для PDF/DOCX/TXT/Markdown/CSV/JSON доступны извлечение текста, профиль документа, таблицы, даты, суммы и bounded-контекст агента. Изображения проходят vision-анализ или OCR fallback; видео объединяет кадры и расшифровку аудиодорожки. Изменённые TXT, Markdown, CSV, JSON и DOCX возвращаются как скачиваемые файлы.

Следующие реальные улучшения computer vision: layout-aware редактирование PDF, сравнение версий документов, координаты объектов и OCR рукописного текста.

`POST /api/v1/chat/document/compare` принимает multipart-файлы `before` и
`after`, извлекает текст и возвращает добавленные/удалённые строки без
расхода AI-кредитов.

### Карты и геолокация

Mobile уже получает координаты только после явного разрешения пользователя и
передаёт их в chat payload. Инструмент `map_geocode` использует Yandex
Geocoder для адресов и мест; сначала берётся `YANDEX_MAPS_API_KEY`, затем
`YANDEX_SEARCH_API_KEY` как совместимый fallback. Один общий ключ Yandex Cloud
сработает только если в кабинете включён сервис Geocoder/API Maps — наличие
ключа для Web Search само по себе этого не гарантирует.

В актуальной конфигурации используется `YANDEX_MAPS_GEOCODER_API_KEY`. API
поиска организаций пока не включён: в кабинете он заблокирован по суточному
лимиту и имеет статус «Без тарифа».

### Vision quality layer

`services.vision_quality` нормализует confidence, строит безопасный план
layout-aware правок, сравнивает версии документов, нормализует bounding boxes,
извлекает пары label/value из графиков и временные кандидаты событий видео.
Наблюдения ниже порога confidence не считаются фактами и требуют подтверждения.

Для видео media pipeline передаёт vision длительность, число кадров, покрытие
и сигнал необходимости досэмплирования. Музыкальный анализ использует строгий
контракт: название, исполнитель, жанр, настроение, инструменты, BPM,
структура, lyrics и таймкоды остаются пустыми, пока модель их не подтвердила.
Map tools: `map_geocode`, `map_search_organizations`, `map_route`, and
`map_distance`. Organization and route calls use dedicated keys and return a
controlled unavailable result when a provider limit is exhausted.
Полный canonical inventory хранится в `utils/capability_catalog.py` и
используется capability-ответом ALTER, поэтому UI, документация и модель могут
сверяться с одним техническим источником.
## Current verified document and agent behavior

### Document editing parity

Documents are analyzed through `POST /api/v1/chat/document` and edited through
`POST /api/v1/chat/document/edit`. Web and mobile use this HTTP contract;
Telegram uses the same attachment pipeline and returns the result in the same
chat. The original request, extracted context, attachment metadata and later
instructions remain in one session, so a follow-up edit does not create a new
chat or fall back to an older attachment.

Each successful edit creates an owner-scoped artifact with a TTL. The response
exposes `artifact_id`; `GET /api/v1/artifacts/{artifact_id}` downloads the latest
version. Supported formats are PDF, DOCX, TXT, Markdown, CSV and JSON. Empty or
unsupported files, scanned PDFs without a text layer, and save failures return
controlled errors and do not claim a completed edit.

ALTER accepts plans with up to 64 tasks. The execution endpoint limits one
request to 8 steps, so larger plans continue in bounded batches. Production
verification completed a real 64-step ordinary-agent plan with one attempt per
task and external actions disabled.

Document editing returns TXT, Markdown, CSV, JSON, DOCX and searchable
text-layer PDF files. PDF replacements are applied at text coordinates and the
result is returned as a valid PDF. Scanned PDFs without a text layer require
OCR and are rejected safely. Successful edits expose an owner-scoped
`artifact_id` and can be downloaded from `/api/v1/artifacts/{artifact_id}`.
