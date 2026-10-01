# ALTER production readiness

Актуально на 2026-10-01.

## Уже закрыто

- ALTER и Gym деплоятся раздельно; Gym владеет host-портами 80/443.
- ALTER проксируется через `web_network`; `alter_bot` не публикует порт наружу.
- `/health`, `/ready`, deploy health wait и production smoke.
- Последний baseline: 573 backend-теста; web — 9 тестов и production build; mobile TypeScript и 18 тестов.
- Квоты: Personal 1000, Ego 5000 кредитов в месяц; Telegram и mobile используют общий Redis-счётчик.
- PostgreSQL backup, облачное хранение и restore drill предусмотрены скриптами проекта.
- Целевые RPO/RTO: RPO до 24 часов (ежедневный backup, off-site копия проверяется monitor), RTO до 60 минут (пересоздание compose и восстановление на отдельную БД/том).

## Эксплуатация подтверждена

- YooKassa привязана, реальные оплаты выполнены и проверены.
- Ежедневные резервные копии выгружаются в Yandex Object Storage.
- Restore drill выполнен дважды за последнюю неделю, оба раза успешно.
- Восстановление выполняется на отдельной тестовой базе, рабочая база не затрагивается.
- Redis ограничен 256 MB с политикой `noeviction`; Docker-логи ограничены 10 MB × 3 файла.
- Prompt-injection защита проверяет также русские инструкции во внешнем контенте.
- Streaming timeout — 30 секунд; web сохраняет частичный ответ при обрыве потока.

## Осталось поддерживать

1. Запускать production smoke после каждого деплоя.
2. Периодически повторять restore drill.
3. Сверять платежи YooKassa с локальными записями.
4. Следить за сроком действия внешних API-ключей и лимитами провайдеров.
5. Для мобильных push-релизов использовать Development Build/TestFlight, а не Expo Go.

## Физический ALTER

План Raspberry Pi и ESP32 находится в [ALTER_PHYSICAL_VOICE_PROTOTYPE.md](ALTER_PHYSICAL_VOICE_PROTOTYPE.md).
Актуальный пошаговый статус — в [docs/CURRENT_STATUS_2026-10-01.md](docs/CURRENT_STATUS_2026-10-01.md).

## Полезные команды

```bash
cd /root/alter
./scripts/production-smoke.sh
./scripts/backup-db-to-s3.sh
LATEST=$(find /root/alter/backups -maxdepth 1 -type f -name 'alter-*.dump' -printf '%T@ %p\n' | sort -nr | head -n1 | cut -d' ' -f2-)
./scripts/restore-drill.sh "$LATEST"
```
