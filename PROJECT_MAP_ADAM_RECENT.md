# ALTER — recent implementation map

## 2026-08-07

- Mobile now has a premium dark permission card shown once per session. It explains the value of notifications and location; system permission dialogs appear only after the user accepts. “Later” closes the card for the session.
- Registration includes an explicit legal consent checkbox with links to the privacy policy and offer. Native blue buttons were replaced with ALTER-styled controls.
- Telegram media messages expose human-readable actions: analyze, improve photo, and animate video. Photo improvement uses the shared generation pipeline. Video stays asynchronous until a real provider file is returned.
- fal.ai configuration: `MEDIA_PROVIDER=fal`, `FAL_BASE_URL=https://fal.run`, `fal-ai/flux-pro/kontext/max` for images, and `fal-ai/kling-video/v2.1/master/image-to-video` for video. API keys stay only in `.env`.
- Mobile launch: `npx expo start --offline --port 8082 -c`. Expo does not allow `--offline` together with `--lan`; run the command in a visible terminal when a QR code is needed.
- VPS update: `git pull --ff-only origin master`, then `docker compose up -d --build bot alter-nginx`; inspect with `docker compose logs --since=2m --tail=100 bot`.
- Verified baseline: 243 backend tests, 13 mobile tests, TypeScript, Python compilation, and `git diff --check` pass.
