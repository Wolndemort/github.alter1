# ALTER final audit

Updated: 2026-08-12

## Product surfaces

- Shared chat and streaming API.
- Mobile Expo client with text, voice, media, documents, memory, reminders, check-ins, calendar, location, workflow and media jobs.
- Telegram client with the same core session, memory, document, audio and media-job flows.
- Durable multi-step agent with executor, workflow state and background monitors.

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

- Backend: `476 passed`.
- Mobile: `23/23` tests.
- Mobile TypeScript: clean.
- Deterministic quality benchmark: `7/7`.
- Middleware/API targeted checks: green.
- Public production smoke: `/health=200`, `/ready=200`, unauthenticated stream=`401`, malformed webhook=`400`.

## Remaining operational work

1. Repeat production smoke after every deployment.
2. Track p50/p95/p99 by auth, quota, DB, model first token, full reply and TTS stages.
3. Reconcile YooKassa payment records periodically with the provider.
