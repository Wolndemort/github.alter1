# ALTER: возможности, API и сценарии

Единая карта возможностей ALTER для mobile и Telegram. Оба клиента используют общий backend, сессии, память и Redis-квоты.

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
| Очистка голоса | POST /api/v1/audio/isolate или подпись к аудио | Да | Да | ElevenLabs Audio Isolation |
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

Sound Effects и Audio Isolation подключены как пользовательские workflow. Music Generation, Dubbing и Voice Generation пока не подключены к естественным командам и не рекламируются как готовые функции.

## Fal.ai

Fal используется для генерации и изменения изображений/видео. Настройки: MEDIA_PROVIDER=fal, MEDIA_GENERATION_API_KEY, FAL_IMAGE_MODEL, FAL_VIDEO_MODEL. Запросы проходят через POST /api/v1/media/generate; результат считается успешным только после получения готового файла.

## Экономика

- текст — 1 кредит;
- голосовой ответ — 5 кредитов;
- media analysis — 20 кредитов;
- media generation — 40 кредитов;
- YouTube search/audio — отдельные кредиты;
- Sound Effects, Audio Isolation и audio mix — 20 кредитов за операцию;
- Personal — 1000 кредитов;
- Ego — 5000 кредитов.

Владелец получает доступ без подписки, но внешние провайдеры сохраняют собственные лимиты и стоимость.

## Правило parity

Новую возможность сначала добавляем в service/API слой, затем подключаем к mobile и Telegram. Для каждого нового внешнего API обязательны auth, owner/subscription check, quota charge, timeout, обработка ошибок, fallback где уместно и contract tests.

## Следующие routes ElevenLabs

- audio effects — Sound Effects;
- audio isolate — Audio Isolation;
- speech-to-speech / voice generation;
- dubbing как асинхронная задача;
- music generation как отдельный дорогой media action.
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
