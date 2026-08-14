# ALTER — итоговый benchmark

Дата сводки: 2026-08-14. Это benchmark продукта ALTER в его российском сценарии использования, а не общий рейтинг базовых языковых моделей.

## 1. Сравнение качества на одинаковых 75 сценариях

Сценарии включали русский разговорный стиль, поддержку, принятие решений, память, напоминания, календарь, документы, web-поиск, YouTube, локальные платежи, приватность и workflows. Запросы отправлялись реальным внешним сервисам, ответы оценивались одной и той же проверкой.

| Система | Пройдено | Pass rate | Средний score | P50 | P95 |
|---|---:|---:|---:|---:|---:|
| ALTER | 75/75 | 100.0% | 98.0 | 14.05 с | 30.00 с |
| ChatGPT | 69/75 | 92.0% | 92.7 | 5.17 с | 26.87 с |
| Gemini | 68/75 | 90.7% | 89.7 | 7.20 с | 16.74 с |

В этом наборе ALTER опередил ChatGPT на 8 процентных пунктов по pass rate и Gemini на 9.3 пункта. По score преимущество составило 5.3 и 8.3 пункта соответственно.

Наиболее сильная сторона ALTER — не абстрактная генерация текста, а связка «русский диалог + память + действия + локальные сервисы». Это сравнение нельзя интерпретировать как победу над ChatGPT/Gemini во всех языках и всех задачах.

## 2. Актуальная скорость production

Источник: `speed_benchmark_final.json`, 3 прогона production API `https://api.alterai.ru`.

| Операция | Запросов | Успешно | Среднее | P50 | P95 |
|---|---:|---:|---:|---:|---:|
| Text streaming, первый токен | 9 | 9/9 | 2.03 с | 2.03 с | 3.13 с |
| Text streaming, полный ответ | 9 | 9/9 | 2.03 с | 2.03 с | 3.14 с |
| Voice reply | 6 | 6/6 | 0.70 с | 0.55 с | 1.16 с |

Voice — ключевой результат: медианное время около 0.5 секунды, максимальное в прогоне — 1.16 секунды. По голосу ALTER выглядит особенно конкурентоспособно.

Старый сравнительный benchmark на 75 сценариях измерял полное завершение сложного ответа и давал ALTER более высокий P50 около 14 секунд. Это другая методика, поэтому её нельзя смешивать с актуальным first-token speed benchmark: сложные сценарии с tools и поиском дольше, короткий streaming-ответ — существенно быстрее.

## 3. Возможности продукта

### Диалог и память

- обычный и streaming text chat;
- долговременная память с подтверждением и удалением;
- контекст между Telegram и mobile;
- новые сессии, feedback, private mode;
- durable-agent: задачи, зависимости, дедлайны, приоритеты, replan и gate внешних действий.

### Поиск и локальная инфраструктура

- Yandex Search, Tavily, Firecrawl, YouTube;
- погода и источники;
- Yandex geocoder, организации, маршруты и distance matrix;
- location context только после разрешения пользователя;
- YooKassa и рублёвая подписка.

### Документы, vision, video и audio

- PDF, DOCX, XLSX, PPTX, ODT, RTF, TXT, Markdown, CSV, JSON;
- OCR, профилирование документов, bounded context и document-agent;
- редактирование и экспорт, сравнение версий, owner-scoped artifact ID;
- image analysis, structured visual audit, chart/object geometry и confidence gate;
- video frames, audio extraction, transcription, timestamped events, image-to-video и video generation;
- speech-to-text, text-to-speech, voice change, isolation, sound effects, audio mix и YouTube audio.

### Productivity и operations

- reminders, follow-up, push и check-ins;
- Google Calendar;
- quotas, quality gate, fallback models, latency diagnostics;
- Redis, PostgreSQL, backups, off-site backup, restore drill, health/ready и production smoke.

## 4. Квоты и экономика

| Тариф | Цена | Квота |
|---|---:|---:|
| Trial | 0 ₽ | 40 кредитов / 3 дня |
| Personal | 990 ₽/мес. | 1000 кредитов |
| Ego | 2990 ₽/мес. | 3500 кредитов |

Основные расходы: текст — 1 кредит, voice reply — 5, media analysis — 20, обычная media generation — 40, text-to-image — 100, text-to-video — 250, YouTube search — 1, YouTube audio — 10.

Платные HTTP-запросы защищены обязательным `Idempotency-Key`; повтор не должен повторно списывать кредит. Ошибка provider path возвращает резерв.

## 5. Надёжность продукта

- backend test suite: 517 passed, 2 skipped;
- mobile TypeScript: passed;
- mobile Jest: 26 passed;
- concurrency tests: один победитель на 40 одинаковых idempotency-запросов, quota limit соблюдается при параллельных списаниях, повторные refund не уводят баланс ниже нуля;
- restore drill последнего PostgreSQL dump прошёл на отдельной `alter_restore_drill`;
- production `/health`, `/ready`, authenticated `/account` и smoke — 200/passed;
- TLS certificate valid through 2026-11-03, HSTS и security headers включены.

## 6. Ограничения benchmark

1. Сравнение 75 сценариев — прикладной тест ALTER, а не независимый академический leaderboard.
2. У моделей могли отличаться провайдеры, лимиты и сетевые условия.
3. Голосовой P50 основан на 6 production запросах; это сильный сигнал, но не окончательная статистика для миллиона запросов.
4. Полезность памяти, поиска и документов измеряется поведением всей системы, а не только моделью.
5. Перед публичным масштабированием нужно продолжать собирать реальные retention, cost per user, provider failure rate и paid conversion.

## Итог

В целевом сценарии российского персонального AI-ассистента ALTER уже показывает конкурентное преимущество по прикладному качеству и функциональной широте, а voice pipeline — особенно сильный показатель по скорости. Следующий объективный этап — не доказывать benchmark бесконечно, а подтвердить его на первых платящих пользователях и удержании.
