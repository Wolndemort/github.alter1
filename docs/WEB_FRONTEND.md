# ALTER Web frontend

The web client lives in `web/` and uses the same authenticated `/api/v1/*`
contract as mobile. It does not contain memory, billing, quota, agent, or
Telegram business rules; those remain in the existing backend services.

## Local development

```text
cd web
npm install
npm run dev
```

The Vite client uses same-origin `/api` by default. A local API can be
selected with `VITE_API_BASE_URL` in the shell environment; no repository
`.env` files are required.

## Current contract map

- Auth/session: register, login, email verification, logout, token rotation.
- Conversation: history, new session, SSE chat stream, multipart media and
  document processing/editing.
- Context: account, memory/audit/confirmation/deletion, my day, settings,
  reminders, workflow and durable agent.
- Access: usage, trial/subscription state, YooKassa payment URL and Telegram
  account linking.
- Media/audio: media jobs, image/video generation, artifacts and the existing
  audio/voice endpoints.
- Discovery: capabilities, FAQ, YouTube and calendar endpoints.

The web client reads the same canonical `GET /api/v1/capabilities` catalog and
`reply` contract as mobile and Telegram. Its chat supports document analysis and
editing, audio uploads, TTS voice replies and media generation; capabilities
that are unavailable with the configured provider key are not advertised by
the canonical catalog.

Mobile is the UX reference for the shared interaction model. Web mirrors its
document artifact editing, sequential latest-version downloads, audio
transcription/processing/speech-to-speech actions, voice generation and
YouTube-audio actions. The web layout remains touch-first below 760px, with
safe-area spacing and 44px-class controls for phone browsers.

The production nginx container builds the web image from this directory. The
existing API remains proxied to `alter_bot`; legal pages remain mounted from
`legal/`.
