# ALTER — инструкция по API и командам

Этот файл описывает фактически подключённые возможности проекта. Telegram,
mobile и HTTP API используют общий backend, память, сессии и лимиты.

Секреты (`BOT_TOKEN`, API-ключи, пароли и `APP_AUTH_SECRET`) не должны
попадать в этот файл, приложение или сообщения пользователям.

## Как работает текст и голос

Текстовую команду можно написать в Telegram, отправить в мобильном чате или
передать в `POST /api/v1/chat/messages`.

Голосовую команду можно отправить голосовым сообщением в Telegram или как
multipart-файл в `POST /api/v1/chat/media`. ALTER сначала расшифровывает её
через Whisper (`TRANSCRIPTION_MODEL`), затем отправляет полученный текст в тот
же обработчик намерений. Поэтому команды должны звучать естественно:

```text
Какая погода сегодня в Москве?
Запомни, что я изучаю Python
Создай звук дождя по стеклу
Почисти эту запись от шума
Наложи звук леса на моё голосовое
Найди на YouTube звуки дождя и пришли аудио
```

Голосовой ввод не означает автоматический голосовой ответ. Для голосового
ответа включите `voice_replies` в настройках или попросите: «озвучь ответ».

## Авторизация приложения

```text
POST /api/v1/auth/register
POST /api/v1/auth/verify-email
POST /api/v1/auth/resend-verification
POST /api/v1/auth/login
GET  /api/v1/auth/me
```

Пример входа:

```bash
curl -X POST "$API/api/v1/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"email":"user@example.com","password":"your-password"}'
```

Далее используйте:

```bash
Authorization: Bearer <access_token>
```

## Fal.ai: генерация с нуля

Добавлены отдельные text-модели:

```text
FAL_TEXT_IMAGE_MODEL=fal-ai/flux-pro/v1.1-ultra
FAL_TEXT_VIDEO_MODEL=fal-ai/kling-video/v2.1/master/text-to-video
```

## ElevenLabs: доступные по ключу обращения

По текущему ключу доступны Text-to-Speech, Speech-to-Text, Speech-to-Speech,
Sound Effects, Voice Generation, чтение Voices и Models. Примеры:

```text
Расшифруй это голосовое
Измени мой голос на голос <название/voice_id>
Создай новый голос: спокойный низкий мужской голос для подкаста
Какие голоса и модели ElevenLabs доступны?
Озвучь этот текст голосом ALTER
Создай звук дождя по стеклу
```

Маршруты:

```text
POST /api/v1/audio/speech-to-text
POST /api/v1/audio/speech-to-speech?voice_id=<id>
POST /api/v1/audio/voice-generation
GET  /api/v1/audio/voices
GET  /api/v1/audio/models
```

Audio Isolation, Music Generation и Dubbing по текущему ключу отключены и не
считаются рабочими возможностями ALTER. Существующий isolation endpoint
оставлен для совместимости, но без включения разрешения ElevenLabs вернёт
ошибку провайдера.

Стоимость операций:

```text
Редактирование фото/оживление фото: 40 кредитов
Генерация изображения с нуля: 100 кредитов
Генерация видео с нуля: 250 кредитов
Owner: 0 кредитов и без уменьшения Redis-счётчика
```

Эти значения настраиваются переменными `MEDIA_GENERATION_CREDITS`,
`FAL_TEXT_IMAGE_CREDITS` и `FAL_TEXT_VIDEO_CREDITS` в `.env`.

Теперь можно написать или сказать голосом без файла:

```text
Создай фотореалистичное фото девушки в вечернем городе, вертикально 9:16
Сгенерируй видео на 5 секунд: камера летит над ночным городом, с звуком
```

Редактирование фото и оживление фотографии используют прежние image-to-image
и image-to-video модели. Команды без исходного файла используют новые
text-to-image и text-to-video модели.

## Чат, голос и медиа

```text
POST /api/v1/chat/messages
POST /api/v1/chat/new
GET  /api/v1/chat/history
POST /api/v1/chat/media
POST /api/v1/media/generate
POST /api/v1/voice/reply
```

Текстовый чат:

```bash
curl -X POST "$API/api/v1/chat/messages" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"message":"Какая погода сегодня?","location":{"city":"Москва"}}'
```

Голос, фотография или видео через multipart:

```bash
curl -X POST "$API/api/v1/chat/media" \
  -H "Authorization: Bearer $TOKEN" \
  -F 'message=Проанализируй этот файл' \
  -F 'file=@voice.m4a'
```

Для голосового файла ответ содержит `transcript`. Для audio-actions он также
может содержать `audio_base64`, `audio_filename` и `audio_mime`.

## ElevenLabs

```text
POST /api/v1/audio/sound-effects
POST /api/v1/audio/isolate
POST /api/v1/audio/process
```

Создать эффект:

```bash
curl -X POST "$API/api/v1/audio/sound-effects" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"rain on a window, calm cinematic atmosphere"}' \
  --output rain.mp3
```

Очистить голос:

```bash
curl -X POST "$API/api/v1/audio/isolate" \
  -H "Authorization: Bearer $TOKEN" \
  -F 'file=@voice.m4a' \
  --output clean.mp3
```

Единая естественная команда для эффекта, очистки и микса:

```bash
curl -X POST "$API/api/v1/audio/process" \
  -H "Authorization: Bearer $TOKEN" \
  -F 'prompt=Наложи звук дождя на моё голосовое' \
  -F 'file=@voice.m4a'
```

В Telegram те же операции выполняются текстом, подписью к voice или второй
голосовой командой, относящейся к предыдущему voice.

## Как пользоваться Fal.ai options в Telegram

Для распространённых параметров достаточно написать их словами в подписи к
фото или видео:

```text
Сделай вертикальный формат, 9:16, seed 42, сохрани в png
Оживи на 10 секунд, 16:9, с звуком
Оживи вертикально, на 5 секунд, без звука, без людей
```

ALTER распознаёт формат кадра, seed, PNG/JPEG/WebP, длительность 5/10
секунд, генерацию аудио и negative prompt. Сложные параметры
(`camera_control`, masks, trajectories, `tail_image_url` и другие) передаются
JSON-полем `options` через HTTP или аргументом `options` в
`api.generateMedia(..., options)` в mobile.

Озвучка текста:

```text
POST /api/v1/voice/reply
JSON: {"text":"Текст для озвучки"}
```

Эта операция возвращает `audio/wav`. Настройка `tts_voice=elevenlabs`
включает ElevenLabs TTS, если `ELEVENLABS_ENABLED`, voice id и ключ настроены.
Music Generation и Dubbing в текущем коде не подключены.

## Fal.ai

Текущая конфигурация:

```text
MEDIA_PROVIDER=fal
FAL_IMAGE_MODEL=fal-ai/flux-pro/kontext/max
FAL_VIDEO_MODEL=fal-ai/kling-video/v2.1/master/image-to-video
```

Единый маршрут:

```text
POST /api/v1/media/generate
GET  /api/v1/media/capabilities
multipart: message, kind=image|video, file, options=JSON
```

`GET /api/v1/media/capabilities` возвращает текущие модели, режимы,
обязательность исходного файла и допустимые поля `options`. Этот маршрут не
возвращает ключ Fal.ai и не списывает кредиты:

```bash
curl "$API/api/v1/media/capabilities" \
  -H "Authorization: Bearer $TOKEN"
```

Текущие модели требуют исходное изображение:

- `flux-pro/kontext/max` — image-to-image редактирование;
- `kling-video/v2.1/master/image-to-video` — анимация изображения.

Редактирование фото:

```bash
curl -X POST "$API/api/v1/media/generate" \
  -H "Authorization: Bearer $TOKEN" \
  -F 'kind=image' \
  -F 'message=Сделай кинематографичный ночной стиль' \
  -F 'file=@photo.jpg' \
  -F 'options={"aspect_ratio":"9:16","seed":42,"output_format":"png"}'
```

Оживление изображения:

```bash
curl -X POST "$API/api/v1/media/generate" \
  -H "Authorization: Bearer $TOKEN" \
  -F 'kind=video' \
  -F 'message=Плавное движение камеры, дождь и ветер' \
  -F 'file=@photo.jpg' \
  -F 'options={"duration":"5","aspect_ratio":"9:16","generate_audio":true}'
```

### Все доступные параметры текущих моделей

Для image-модели `options` поддерживает поля схемы Fal.ai:

```json
{
  "aspect_ratio": "21:9 | 16:9 | 4:3 | 3:2 | 1:1 | 2:3 | 3:4 | 9:16 | 9:21",
  "seed": 42,
  "guidance_scale": 3.5,
  "sync_mode": false,
  "num_images": 1,
  "output_format": "jpeg",
  "safety_tolerance": "2",
  "enhance_prompt": true,
  "image_prompt_strength": 0.8
}
```

Для video-модели:

```json
{
  "duration": "5 | 10",
  "negative_prompt": "blur, distort, low quality",
  "cfg_scale": 0.5,
  "generate_audio": true,
  "shot_type": "customize | intelligent",
  "aspect_ratio": "16:9 | 9:16 | 1:1",
  "tail_image_url": "https://...",
  "static_mask_url": "https://...",
  "dynamic_masks": [],
  "keep_original_sound": false,
  "character_orientation": "image | video",
  "camera_control": {},
  "advanced_camera_control": {}
}
```

Backend сам добавляет `prompt` и `image_url`; эти поля нельзя переопределить
через `options`. Результат возвращается только после загрузки настоящего
файла от Fal.ai: `media_type`, `filename`, `data_base64`.

Команды Telegram для текущего Fal-flow:

```text
Пришли фото и подпиши: «сделай красивее»
Пришли фото и подпиши: «оживи это изображение»
Голосом скажи команду после прикрепления фотографии
```

Text-to-image и text-to-video будут добавлены отдельными моделями после их
включения в конфигурацию Fal.ai. Нельзя использовать текущие image-to-image
и image-to-video endpoints как генерацию с нуля.

## YouTube, поиск и погода

```text
POST /api/v1/youtube/search  {"query":"..."}
POST /api/v1/youtube/audio   {"url":"https://youtube.com/..."}
```

Примеры естественных команд:

```text
Найди на YouTube музыку для дождливого вечера
Найди ролик и пришли аудио
```

Актуальный web-поиск и погода вызываются через обычный чат:

```text
Найди актуальную цену iPhone
Какая погода сегодня в Москве?
```

Внутри используются Tavily и `wttr.in`; прямых пользовательских маршрутов
для них нет.

## Память, настройки, напоминания и аккаунт

```text
GET    /api/v1/account
GET    /api/v1/memory
GET    /api/v1/usage
GET    /api/v1/subscription
PATCH  /api/v1/subscription/auto-renew
DELETE /api/v1/subscription/payment-method
POST   /api/v1/subscription/create-payment
POST   /api/v1/telegram/link
GET    /api/v1/settings
PATCH  /api/v1/settings
POST   /api/v1/checkins
POST   /api/v1/push-token
GET    /api/v1/reminders
POST   /api/v1/reminders
DELETE /api/v1/reminders/{reminder_id}
```

Основные текстовые команды Telegram:

```text
Запомни, что я изучаю Python
Забудь, что я изучаю Python
Напомни завтра в 10:00 позвонить маме
/memory
/new_session
/settings
/status
/usage
/checkins_on
/checkins_off
```

## Ограничения и оплата

Защищённые API требуют Bearer-токен и активную подписку либо owner-доступ.
Операции списывают кредиты согласно тарифу. Размер файла ограничен
`MEDIA_MAX_BYTES` (по умолчанию 20 MB). Секретные внешние API вызываются
только backend-сервисом; мобильное приложение и Telegram не получают ключи.

## Готовые обращения к ALTER

Ниже приведены фразы, которые можно написать или произнести голосом. Для
голоса достаточно отправить voice без подписи: ALTER сама расшифрует речь и
выполнит ту же команду. Если команда относится к прикреплённому файлу,
отправьте файл с подписью или сначала файл, затем голосовую команду.

### Общение и помощь

```text
Объясни простыми словами, что такое Docker
Помоги составить план запуска проекта
Сравни два варианта и предложи лучший
Напиши письмо клиенту в вежливом тоне
Сократи этот текст до пяти пунктов
Переведи этот текст на английский
Проверь мой текст и исправь ошибки
Что ты умеешь?
Как пользоваться ALTER?
```

### Погода и актуальная информация

```text
Какая погода сегодня в Москве?
Будет ли завтра дождь в Санкт-Петербурге?
Какая температура сейчас в Дубае?
Найди актуальную цену iPhone
Что нового произошло сегодня в мире?
Проверь, правда ли эта информация
Найди лучшие варианты по заданным условиям
```

Для погоды можно также использовать Telegram-команду:

```text
/weather Москва
```

### Память

```text
Запомни, что я изучаю Python
Запомни: я не ем молочные продукты
Что ты помнишь обо мне?
Забудь, что я изучаю Python
Очисти мою память
```

Память используется для долгосрочных фактов. ALTER не должна сохранять
каждую случайную фразу без просьбы пользователя.

### Напоминания и check-in

```text
Напомни завтра в 10:00 позвонить маме
Напомни через два часа проверить почту
Поставь напоминание на 20 августа в 18:30 оплатить счёт
Показывай мои напоминания
Отмени напоминание
Включи check-in
Выключи check-in
```

Telegram-команды:

```text
/remind
/reminders
/cancel_reminder
/checkins_on
/checkins_off
```

### Голос и озвучка

```text
Отправить voice: «Какая погода сегодня?»
Озвучь последний ответ
Отвечай мне голосом
Выключи автоматические голосовые ответы
/voice Текст, который нужно озвучить
/voice_on
/voice_off
```

Голосовая команда сначала распознаётся в текст. Если распознавание не удалось,
ALTER сообщит об ошибке и не будет придумывать содержание записи.

### ElevenLabs: звуки и обработка голоса

```text
Создай звук дождя по стеклу
Сгенерируй звук леса ночью
Сделай звук шагов по снегу
Почисти это голосовое от шума
Изолируй мой голос
Наложи звук дождя на моё голосовое
Добавь к записи звук костра на фоне
```

Для наложения отправьте голосовое с подписью либо отправьте голосовое, а
следующей голосовой командой скажите, какой эффект добавить.

### YouTube

```text
Найди на YouTube звуки дождя
Найди песню и пришли аудио
Найди видео с уроком по Python
Найди лучший обзор этого телефона
Скачай аудио по этой YouTube-ссылке
```

Telegram также поддерживает `/youtube` через обычный диалог, если запрос
однозначно относится к поиску видео или музыки.

### Фото и видео: анализ

Прикрепите фото, скриншот или видео и напишите/скажите:

```text
Что изображено на этом фото?
Прочитай текст на скриншоте
Проанализируй этот документ
Что можно улучшить в этом дизайне?
Оцени сочетание одежды и предложи варианты
Разбери этот короткий ролик
```

### Fal.ai: редактирование изображения

Прикрепите фотографию и используйте подпись:

```text
Сделай кинематографичный стиль
Замени фон на ночной город
Сделай вертикальный формат 9:16
Сделай квадрат 1:1 и сохрани в png
Сделай широкое изображение 16:9
Измени одежду на деловой костюм
Добавь мягкий свет и убери лишние детали
Seed 42, сохрани в webp
```

Голосом можно произнести ту же команду после прикрепления фотографии.
Текущая модель Fal.ai редактирует исходное изображение; команда «создай
картинку с нуля» заработает после подключения text-to-image модели.

### Fal.ai: видео из изображения

Прикрепите изображение и напишите/скажите:

```text
Оживи это изображение
Сделай плавное движение камеры
Оживи на 5 секунд
Оживи на 10 секунд в формате 9:16
Добавь звук
Сделай без звука
Оживи, но без людей, текста и размытия
```

Текущая модель является image-to-video. Для видео с нуля без исходного
изображения потребуется отдельная text-to-video модель.

### Системные функции приложения

```text
Покажи мою память
Покажи расход лимита
Покажи статус подписки
Включи автопродление
Отключи автопродление
Свяжи мой аккаунт с Telegram
Начни новый разговор
Покажи все возможности
```

Telegram-команды:

```text
/help
/memory
/new_session
/settings
/status
/usage
/buy
```

### Как формулировать команду правильно

Лучший шаблон:

```text
действие + объект + желаемый результат + параметры
```

Например:

```text
Оживи это фото на 5 секунд, вертикально 9:16, с дождём и звуком
Почисти это голосовое от шума и оставь естественный тембр
Измени это фото: ночной город, кинематографичный свет, формат 16:9
```

Не нужно знать названия API или моделей. Сложные Fal.ai-параметры можно
передать через `options`, но для обычного пользователя достаточно этих
естественных формулировок.
## Web-поиск: Tavily и Firecrawl

ALTER сама выбирает web-поиск, когда вопрос требует актуальных данных. В `.env` укажи `TAVILY_API_KEY`, `FIRECRAWL_API_KEY` и при необходимости `FIRECRAWL_SEARCH_LIMIT=5`. Ключи не публикуй в документации или чате.

Называть сервисы в сообщении не нужно. Примеры для Telegram, мобильного чата и голосового ввода:

```text
Найди актуальную цену iPhone и сравни несколько источников
Проверь эту новость по нескольким сайтам
Изучи эту страницу и кратко перескажи: https://example.com
Найди официальную документацию по FastAPI и дай ссылки
Что нового произошло сегодня?
Сколько кредитов стоит web-поиск?
```

Tavily выполняет углублённый поиск, Firecrawl дополнительно извлекает содержимое найденных страниц. Результаты объединяются, дубли по URL удаляются; при отказе одного сервиса второй продолжает работать. Обычный разговор и вопросы о памяти поиск не запускают.

Голосовое сообщение сначала распознаётся в текст, затем выполняется как обычная команда. При ошибке распознавания ALTER не придумывает содержание записи.

Поиск обычно списывает 1 кредит. Точные квоты можно спросить фразой «покажи мои квоты» или командой `/usage`; владелец работает без списания кредитов.
### Важно: результаты поиска и месячная квота Firecrawl

`FIRECRAWL_SEARCH_LIMIT=10` означает максимум 10 найденных страниц в одном запросе. Это не означает 10 списаний и не уменьшает месячную квоту на 10 единиц. Значение можно изменить в `.env`, но backend ограничивает одну выдачу разумным максимумом, чтобы не переполнять контекст ALTER.

Месячная квота Firecrawl/Tavily контролируется самим внешним аккаунтом провайдера. Если в кабинете Firecrawl доступно 1000 единиц на месяц, ALTER сможет использовать их до исчерпания. Owner освобождён от внутренних кредитов ALTER, но не может обойти лимит или баланс Firecrawl/Tavily: внешний API всё равно вернёт ошибку, если его месячная квота закончилась.

Внутренние кредиты ALTER и внешняя квота — разные вещи:

- кредит ALTER — расчётный лимит пользователя внутри приложения;
- квота Firecrawl — лимит ключа во внешнем сервисе;
- owner не тратит кредиты ALTER;
- owner всё равно использует общий Firecrawl/Tavily-ключ и его внешнюю квоту.

Для усиленного поиска ALTER одновременно обращается к Tavily и Firecrawl, объединяет результаты, убирает дубли и продолжает работу при отказе одного источника.
## Google Calendar

ALTER может подключить личный Google Calendar через OAuth. В Google Cloud нужно создать OAuth Client типа `Web application` и добавить redirect URI:

```text
https://api.alterai.ru/api/v1/calendar/oauth/callback
```

В основной `.env` добавляются значения из скачанного JSON-файла Google:

```env
GOOGLE_CLIENT_ID=вставь_client_id
GOOGLE_CLIENT_SECRET=вставь_client_secret
GOOGLE_REDIRECT_URI=https://api.alterai.ru/api/v1/calendar/oauth/callback
```

Пользовательские команды Telegram:

```text
/calendar_connect — получить ссылку и подключить Google Calendar
/calendar — показать ближайшие события
/calendar_add 2026-08-20 10:00 2026-08-20 11:00 встреча — создать событие
```

В мобильном приложении используется тот же backend: `GET /api/v1/calendar/connect` возвращает OAuth-ссылку, после подключения доступны `GET /api/v1/calendar/status`, `GET /api/v1/calendar/events`, `POST /api/v1/calendar/events` и `DELETE /api/v1/calendar/events/{event_id}`. OAuth подключается отдельно каждым пользователем; ALTER получает только выбранные права Calendar и не видит пароль Google.
