# Quotas, payments and unit economics

ALTER uses one monthly Redis credit counter shared by the mobile app and Telegram. Credits are reserved atomically before an expensive provider call and refunded when the provider or queue fails.

| Operation | Cost |
|---|---:|
| Text chat/document analysis | 1 |
| Voice reply/TTS | 5 |
| Media analysis | 20 |
| Audio actions/ElevenLabs media | 20 |
| Image generation | 100 |
| Video generation | 250 |
| YouTube search/audio | configured separately in `.env` |

Plans are configured by `PERSONAL_MONTHLY_CREDITS` and `EGO_MONTHLY_CREDITS`. The current product defaults are Personal `1000` and Ego `3500`; always use the active server `.env` as the source of truth.

Payment safety:

- YooKassa requests use an idempotence key.
- Webhook activation validates payment id, user id, metadata, amount and status.
- Repeated successful webhooks are harmless.
- Recurring payment failures disable auto-renewal.
- Provider failures refund reserved credits.
- Media cancellation refunds the reservation.
- All expensive authenticated POST routes accept `Idempotency-Key`; duplicate requests return `409` instead of charging twice. Failed requests release the key for retry.
- Owner access bypasses subscription and credit charging by explicit configured owner identity.

Useful commands:

```powershell
# Read current usage with a temporary token
$env:AUTH_TOKEN = (Get-Content .audit-token -Raw).Trim()
curl https://api.alterai.ru/api/v1/usage -H "Authorization: Bearer $env:AUTH_TOKEN"
Remove-Item Env:AUTH_TOKEN
```

Never commit `.env`, `.audit-token`, provider keys or benchmark output containing private data.
