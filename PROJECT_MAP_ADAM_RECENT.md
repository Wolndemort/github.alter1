# ALTER — recent implementation map

## 2026-08-07

- Mobile now has a premium dark permission card shown once per session. It explains the value of notifications and location; system permission dialogs appear only after the user accepts. “Later” closes the card for the session.
- Registration includes an explicit legal consent checkbox with links to the privacy policy and offer. Native blue buttons were replaced with ALTER-styled controls.
- Telegram media messages expose human-readable actions: analyze, improve photo, and animate video. Photo improvement uses the shared generation pipeline. Video stays asynchronous until a real provider file is returned.
- fal.ai configuration: `MEDIA_PROVIDER=fal`, `FAL_BASE_URL=https://fal.run`, `fal-ai/flux-pro/kontext/max` for images, and `fal-ai/kling-video/v2.1/master/image-to-video` for video. API keys stay only in `.env`.
- Mobile launch: `npx expo start --offline --port 8082 -c`. Expo does not allow `--offline` together with `--lan`; run the command in a visible terminal when a QR code is needed.
- VPS update: `git pull --ff-only origin master`, then `docker compose up -d --build bot alter-nginx`; inspect with `docker compose logs --since=2m --tail=100 bot`.
- Verified baseline: 243 backend tests, 13 mobile tests, TypeScript, Python compilation, and `git diff --check` pass.

## 2026-08-11

- Release baseline: 370 backend tests and 19 mobile tests pass locally.
- Web/tool requests use SSE with status events and token-streamed final answers; independent tools run in parallel with timeout and cancellation.
- Added private mode, full personal-data deletion, workflow progress, safe action-log with tool attribution, p50/p95 latency diagnostics and token telemetry.
- Russian eval v1 and benchmark helpers live in `evals/`, `utils/benchmark.py`, `scripts/collect_alter_benchmark.py` and `scripts/score_benchmark.py`.
- Production is served through `api.alterai.ru` / `77.73.131.175`; deploy only after batching changes and running the full local suite.

## 2026-08-17

- SEO production layer is live on `alterai.ru`. Public crawlable pages: `/`, `/vozmozhnosti`, `/faq`, `/privacy`, and `/offer`.
- `web/public/robots.txt` allows public pages, blocks `/api/`, and points crawlers to `https://alterai.ru/sitemap.xml`.
- `web/public/sitemap.xml` lists the public SEO pages. `web/index.html` contains the canonical URL, Russian title/description, Open Graph/Twitter metadata, `SoftwareApplication` JSON-LD, and a no-JavaScript text fallback.
- Nginx serves `/faq` and `/vozmozhnosti` as real static HTML pages; `/features` redirects to `/vozmozhnosti`. Do not replace these routes with the authenticated SPA shell.
- Yandex Webmaster ownership is confirmed through `web/public/yandex_c3c352c871be8803.html`; Yandex sitemap submission is complete. Google Search Console ownership is confirmed through DNS TXT and the same sitemap is submitted there.
- SEO verification commands: `Invoke-WebRequest https://alterai.ru/robots.txt`, `Invoke-WebRequest https://alterai.ru/sitemap.xml`, and `Invoke-WebRequest https://alterai.ru/faq` must return 200 with `text/plain`, `text/xml`, and HTML respectively.
- Image search sends a real image preview (up to 5 MB), normalizes provider WebP/error responses to JPEG, keeps image search separate from image generation, and falls back beyond failed Yandex candidates.
- Current repository/deployment rule: commit and push to `master`; production path is `/root/alter`; nginx/other project `/root/github.io-test` must not be changed. Mobile checks remain `cd mobile; npx tsc --noEmit; npm test -- --runInBand`.
