# Benchmark ALTER, ChatGPT и Gemini

Benchmark состоит из двух фаз: сбор одинаковых ответов и offline scoring. Scoring не вызывает провайдеров и не расходует кредиты.

## Сбор ответов ALTER

Требуется временный пользовательский токен в окружении. Токен не выводится и не записывается в результат.

```powershell
$env:AUTH_TOKEN="..."
py -3 scripts/collect_alter_benchmark.py --output alter_results.json --limit 20 --confirm-cost
```

`--confirm-cost` обязателен: каждый кейс отправляет обычный chat-запрос и списывает кредит. Начинай с `--limit 3`.

## Формат ответов других моделей

```json
[
  {"model":"chatgpt","case_id":"small_hello","response":"Привет!","latency_ms":420},
  {"model":"gemini","case_id":"small_hello","response":"Привет!","latency_ms":380}
]
```

Объединённый отчёт:

```powershell
py -3 scripts/score_benchmark.py --input all_results.json --output benchmark_report.json
```

Для ChatGPT или Gemini с OpenAI-compatible endpoint:

```powershell
$env:MODEL_API_KEY="..."
$env:MODEL_NAME="..."
py -3 scripts/collect_compatible_benchmark.py --model-id chatgpt --output chatgpt_results.json --limit 3 --confirm-cost
```

Для Gemini укажи его OpenAI-compatible `MODEL_BASE_URL` и модель Gemini. Ответы
ALTER и внешней модели затем объединяются в один `all_results.json`.

Отчёт содержит pass-rate, средний score, p50/p95 latency и типы проблем: language mismatch, internal leak, missing source attribution и empty response.

Правила: одинаковый набор `evals/russian_v1.json`, одинаковые запросы, ссылки для web-кейсов, полный набор вместо лучших ответов, отдельный учёт стоимости и latency, отсутствие реальных пользовательских данных.

Authenticated production smoke запускается через `scripts/production-e2e.sh`. Без `AUTH_TOKEN` он проверяет public health, ready и auth boundaries; с токеном дополнительно проверяет scenarios, workflow, SSE и action-log.
