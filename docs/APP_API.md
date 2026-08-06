# Independent application API

The mobile application is a parallel client. Telegram polling and `handlers/`
remain separate; shared behavior lives in `services/`, HTTP adapters in `api/`,
and the future React Native client in `mobile/`.

Add this server-side variable before enabling application login:

```dotenv
APP_AUTH_SECRET=replace-with-a-long-random-value
```

Run `alembic upgrade head` after deployment. Migration `0015_web_accounts`
creates application accounts and a PostgreSQL sequence for web-only profiles
without changing existing Telegram IDs.

Endpoints:

```text
POST /api/v1/auth/register   {"email":"...", "password":"..."}
POST /api/v1/auth/login      {"email":"...", "password":"..."}
GET  /api/v1/auth/me         Authorization: Bearer <token>
POST /api/v1/chat/messages   Authorization: Bearer <token>, {"message":"..."}
```

The first slice is text-first. Media, reminders, settings, subscription
cabinet, Telegram linking, and streaming are separate slices so mobile code
does not become coupled to Telegram handlers.

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
   `EXPO_PUBLIC_API_URL=https://api.alterai.ru`, then run `npm install` and
   `npm test` before `npm start`.

The migration is idempotent through Alembic. Do not run `alembic downgrade` on
production. Backups and the existing Telegram polling process are not changed
by this slice.
