# ALTER final audit

Updated: 2026-08-15

## Product surfaces

- Shared chat and streaming API.
- Mobile Expo client with text, voice, media, documents, memory, reminders, check-ins, calendar, location, workflow and media jobs.
- Telegram client with the same core session, memory, document, audio and media-job flows.
- Durable multi-step agent with executor, workflow state and background monitors.
- Ordinary agent plans support up to 64 tasks; production verification completed
  a real 64-step plan in eight bounded batches with one attempt per task.

## Safety and correctness

- User memory is projected through `utils/memory_view.py`; `_meta`, provenance and confidence fields are never rendered as user-facing rows.
- Memory confirmation uses raw storage identifiers while UI labels remain localized.
- Pending reminders accept a time answer without hijacking unrelated messages.
- PDF editing requires a searchable text layer; scanned PDFs need OCR.
- External content is treated as untrusted; SSRF and prompt-injection guards are enabled.
- Middleware covers DB sessions, spam/rate limits, daily request limits, subscription access and Redis failure handling.

## Payments and quotas

See [QUOTAS_AND_UNIT_ECONOMICS.md](QUOTAS_AND_UNIT_ECONOMICS.md). Credit reservations are atomic, provider failures are refundable, and payment activation is idempotent.

## Performance

The HTTP admission middleware caches owner access for 30 seconds. ElevenLabs uses lifecycle-managed persistent HTTP connections and closes them during application shutdown.

Latest production speed sample (15 runs, 45 text and 30 voice requests):

| Metric | Result |
|---|---:|
| Text success | 45/45 |
| Text p50 | 1814 ms |
| Text p95 | 2444 ms |
| Voice success | 30/30 |
| Voice p50 | 443 ms |
| Voice p95 | 1649 ms |

These are observed production samples, not a universal guarantee; provider load and model routing affect tail latency.

## Verification baseline

- Backend: `529 passed, 2 skipped`.
- Mobile: `27/27` tests.
- Mobile TypeScript: clean.
- Web production build: successful.
- Deterministic quality benchmark: `7/7`.
- Middleware/API targeted checks: green.
- Public production smoke: `/health=200`, `/ready=200`, unauthenticated stream=`401`, malformed webhook=`400`.
- Production document E2E: TXT and searchable text-layer PDF edit, natural-language
  artifact reuse without re-upload, and authenticated artifact downloads passed.
- Production audio smoke: TTS, STT, speech-to-speech, sound effects and audio mix
  passed; Audio Isolation was not available because the ElevenLabs key returned
  provider `401` and is not advertised by the capability catalog.
- Non-billing availability load check: 50 requests at concurrency 10, 0 failures, p50 `84.8 ms`, p95 `688.3 ms`.

## Remaining operational work

1. Repeat production smoke after every deployment.
2. Track p50/p95/p99 by auth, quota, DB, model first token, full reply and TTS stages.
3. Reconcile YooKassa payment records periodically with the provider.

The bounded public load check is safe to run without a user token:

```powershell
py scripts/load_smoke.py --base-url https://api.alterai.ru --requests 50 --concurrency 10
```
