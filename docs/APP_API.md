# Independent application API

Public help page:

```text
GET /api/v1/faq
```

It returns the same black-and-white FAQ linked from the mobile menu and
Telegram `/faq` command. It does not require a bearer token.

The mobile application is a parallel client. Telegram polling and `handlers/`
remain separate; shared behavior lives in `services/`, HTTP adapters in `api/`,
and the future React Native client in `mobile/`.

Add this server-side variable before enabling application login:

```dotenv
APP_AUTH_SECRET=replace-with-a-long-random-value
APP_EMAIL_MODE=console
# For real email delivery set APP_EMAIL_MODE=smtp and configure SMTP_* below.
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=...
SMTP_PASSWORD=...
SMTP_FROM_EMAIL=no-reply@example.com
SMTP_USE_TLS=true
```

Run `alembic upgrade head` after deployment. Migration `0015_web_accounts`
creates application accounts and a PostgreSQL sequence for web-only profiles
without changing existing Telegram IDs.

Endpoints:

```text
POST /api/v1/auth/register   {"email":"...", "password":"..."}
POST /api/v1/auth/verify-email {"email":"...", "code":"123456"}
POST /api/v1/auth/resend-verification {"email":"..."}
POST /api/v1/auth/login      {"email":"...", "password":"..."}
GET  /api/v1/auth/me         Authorization: Bearer <token>
POST /api/v1/legal/accept   Authorization: Bearer <token>
POST /api/v1/chat/messages   Authorization: Bearer <token>, {"message":"..."}
POST /api/v1/chat/new        Authorization: Bearer <token>
GET  /api/v1/chat/history    Authorization: Bearer <token>
POST /api/v1/chat/media      Authorization: Bearer <token>, multipart `message` + `file`
POST /api/v1/media/generate  Authorization: Bearer <token>, multipart `message` + `kind` + optional `file`
POST /api/v1/voice/reply     Authorization: Bearer <token>, {"text":"..."}; returns WAV
GET  /api/v1/settings        Authorization: Bearer <token>
PATCH /api/v1/settings       Authorization: Bearer <token>, settings JSON
POST /api/v1/checkins        Authorization: Bearer <token>, {"enabled":true}
POST /api/v1/push-token       Authorization: Bearer <token>, {"token":"ExponentPushToken[...]"}
GET  /api/v1/reminders       Authorization: Bearer <token>
POST /api/v1/reminders       Authorization: Bearer <token>, {"text":"...","remind_at":"...+03:00"}
DELETE /api/v1/reminders/:id Authorization: Bearer <token>
POST /api/v1/youtube/search   Authorization: Bearer <token>, {"query":"..."}
POST /api/v1/youtube/audio    Authorization: Bearer <token>, {"url":"https://youtube.com/..."}
POST /api/v1/audio/sound-effects Authorization: Bearer <token>, {"prompt":"rain on glass"}; returns MP3
POST /api/v1/audio/isolate    Authorization: Bearer <token>, multipart `file`; returns MP3
POST /api/v1/audio/process    Authorization: Bearer <token>, multipart `prompt` + optional `file`; returns JSON with base64 MP3
POST /api/v1/audio/speech-to-text Authorization: Bearer <token>, multipart `file`; returns ElevenLabs transcript JSON
POST /api/v1/audio/speech-to-speech?voice_id=<id> Authorization: Bearer <token>, multipart `file`; returns MP3
GET  /api/v1/audio/voices     Authorization: Bearer <token>
GET  /api/v1/audio/models     Authorization: Bearer <token>
POST /api/v1/audio/voice-generation Authorization: Bearer <token>, {"description":"..."}
GET  /api/v1/account         Authorization: Bearer <token>
GET  /api/v1/memory          Authorization: Bearer <token>
DELETE /api/v1/memory/{category} Authorization: Bearer <token>
DELETE /api/v1/memory         Authorization: Bearer <token>
GET  /api/v1/subscription    Authorization: Bearer <token>
POST /api/v1/subscription/create-payment Authorization: Bearer <token>
POST /api/v1/telegram/link   Authorization: Bearer <token>
```

The application and Telegram use the same `users`, `session`, memory, and
billing records. `POST /api/v1/telegram/link` creates a short-lived deep link;
opening it in Telegram consumes the link once and merges an existing Telegram
profile into the application profile transactionally. Migration `0017` adds
only the nullable Telegram identity link to `web_accounts`.

## Telegram/mobile parity

| Capability | Mobile status | Shared backend path |
|---|---|---|
| Text chat and memory recall | ready | `ChatService` |
| Weather | ready | `ChatService` + weather adapter |
| Tavily/web research | ready through the AI tool loop | shared AI services |
| Photo/video analysis | ready | `/api/v1/chat/media` |
| Voice transcription | ready | `/api/v1/chat/media` |
| Subscription/payment | ready | shared YooKassa records and webhook |
| Telegram linking | ready | Redis one-time deep link |
| Memory cabinet | ready | `/api/v1/memory` |
| Reminders/check-ins/settings | next API slice | existing shared models and tasks |
| YouTube audio workflow | next API slice | existing Telegram adapter logic |

## Server deployment checklist

1. In the server `.env`, add `APP_AUTH_SECRET` with a long random value. Do
   not put this value in the mobile project or commit it.
2. Upload the new code and run the migration from the project directory:

   ```bash
   cd /root/alter
   docker compose run --rm migrations
   ```

3. Recreate the bot container so the API routes and environment are loaded:

   ```bash
   docker compose up -d --build bot alter-nginx
   docker compose ps
   ```

4. Verify the public health endpoint and registration route. A missing secret
   must return `503` for app auth while Telegram still remains operational:

   ```bash
   curl -fsS https://api.alterai.ru/health
   curl -i -X POST https://api.alterai.ru/api/v1/auth/register \
     -H 'Content-Type: application/json' \
     -d '{"email":"test@example.com","password":"change-me-123"}'
   ```

5. In the mobile project, create `mobile/.env` from `.env.example` and set
   `EXPO_PUBLIC_API_URL=https://api.alterai.ru`. `EXPO_PUBLIC_INTRO_SOUND_URL`
   is optional; the offline loading scene works without it. Then run
   `npm install`, `npm test`, and `npm start`.

The migration is idempotent through Alembic. Do not run `alembic downgrade` on
production. Backups and the existing Telegram polling process are not changed
by this slice.

## Quick usage

Protected requests use the token returned by login or email verification:

```bash
TOKEN='...'
curl -X POST "$API/api/v1/chat/messages" -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"message":"Какая погода сегодня?"}'
```

For a sound effect, send a normal chat request such as `Создай звук дождя по
стеклу`. To mix or clean a recording, use multipart; the prompt selects the
operation:

```bash
curl -X POST "$API/api/v1/audio/process" -H "Authorization: Bearer $TOKEN" \
  -F 'prompt=Наложи звук дождя на мое голосовое' -F 'file=@voice.m4a'
```

The response contains `reply`, `audio_base64`, `audio_filename` and
`audio_mime`. The same commands work in Telegram: send a voice message with
a caption, or send a second voice command without a caption to apply it to
the previous voice message. Mobile and Telegram share services, sessions,
memory and quotas.

## Fal.ai

Current production models are `fal-ai/flux-pro/kontext/max` for image-to-image
editing and `fal-ai/kling-video/v2.1/master/image-to-video` for animation.
They both require an input image; text-to-image and text-to-video are not
enabled by the current model configuration. Set `MEDIA_PROVIDER=fal`,
`MEDIA_GENERATION_API_KEY`, `FAL_IMAGE_MODEL` and `FAL_VIDEO_MODEL`.

```bash
curl -X POST "$API/api/v1/media/generate" -H "Authorization: Bearer $TOKEN" \
  -F 'kind=image' -F 'message=cinematic rain at night' -F 'file=@source.jpg'
```

The response contains `media_type`, `filename` and `data_base64`; success is
returned only after fal.ai provides a real artifact. Model-specific controls
can be passed as a JSON `options` multipart field, for example:

```bash
-F 'options={"aspect_ratio":"9:16","seed":42,"output_format":"png"}'
```

Image options include `aspect_ratio`, `seed`, `guidance_scale`, `sync_mode`,
`num_images`, `output_format`, `safety_tolerance`, `enhance_prompt` and
`image_prompt_strength`. Video options include `duration`, `negative_prompt`,
`cfg_scale`, `generate_audio`, `shot_type`, `aspect_ratio`, `tail_image_url`,
`camera_control` and the other fields documented by the configured model.
\n+Mobile document attachments support PDF, DOCX, TXT, Markdown, CSV and JSON.
They are sent to `POST /api/v1/chat/document` with `agent=true`; the response
contains the analysis and an active document agent. TXT/MD/CSV/JSON/DOCX edits
are returned by `POST /api/v1/chat/document/edit`; PDF is readable/comparable
but layout-aware editing remains intentionally disabled.
\n+Telegram документный pipeline принимает PDF, DOCX, TXT, Markdown, CSV и JSON
как вложение с caption, извлекает bounded-текст и профиль документа и отвечает
по содержимому. Лимит — 25 MB.
\n+PDF layout editing uses optional PyMuPDF: text is located by coordinates,
redacted and replaced in the same rectangle. Scanned pages without a text layer
must go through OCR first; the API refuses unsafe blind replacements.
