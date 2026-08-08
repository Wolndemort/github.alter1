# ALTER production readiness

Актуально на 2026-08-08.

## Уже закрыто

- ALTER и Gym деплоятся раздельно; Gym владеет host-портами 80/443.
- ALTER проксируется через `web_network`; `alter_bot` не публикует порт наружу.
- `/health`, `/ready`, deploy health wait и production smoke.
- 249 backend-тестов, тарифные тесты Personal/Ego и webhook YooKassa.
- Квоты: Personal 1000, Ego 5000 кредитов в месяц; Telegram и mobile используют общий Redis-счётчик.
- PostgreSQL backup, облачное хранение и restore drill предусмотрены скриптами проекта.

## Перед продажами

1. Выполнить реальный тестовый платёж Personal и Ego в YooKassa.
2. Проверить `payment.succeeded`, `payment.canceled` и повторный webhook.
3. Проверить один restore drill на сервере.
4. Убедиться, что cron backup и monitor уже существуют на VPS.
5. Проверить mobile Expo Go; для push и публикации нужен Development Build и отдельный Apple Developer Program.

## Полезные команды

```bash
cd /root/alter
./scripts/production-smoke.sh
./scripts/backup-db-to-s3.sh
LATEST=$(find /root/alter/backups -maxdepth 1 -type f -name 'alter-*.dump' -printf '%T@ %p\n' | sort -nr | head -n1 | cut -d' ' -f2-)
./scripts/restore-drill.sh "$LATEST"
```
