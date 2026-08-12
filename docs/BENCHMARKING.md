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

## Text and voice speed benchmark

Use the reproducible speed collector for multiple production samples. It
stores only timings, HTTP statuses and audio byte counts; prompts and replies
are not written to the report, and the token is never printed.

```powershell
$env:AUTH_TOKEN = (Get-Content .audit-token -Raw).Trim()

# Windows PowerShell equivalent
.\scripts\production-e2e.ps1
py scripts/collect_speed_benchmark.py --output speed_benchmark.json --runs 3 --confirm-cost
```

Each run contains three text SSE cases and two voice cases. Compare text
`first_token_ms` and `total_ms` separately from voice `total_ms`; voice is an
ALTER capability benchmark and has no ChatGPT/Gemini baseline in this suite.

### What p50 and p95 mean

The `p` means percentile. `p50` is the median: half of requests completed
faster and half slower. `p95` is the tail latency: 95% completed within this
time, while the slowest 5% took longer. p50 shows the normal user experience;
p95 exposes cold starts, provider stalls and fallback delays. We track both
so one exceptionally fast answer cannot hide rare 20–30 second delays.

### Complete benchmark map

```powershell
# Local quality and regression suite (no provider calls)
py -m pytest -q
py -m compileall -q .

# ALTER vs ChatGPT/Gemini quality benchmark (paid; explicit confirmation)
$env:AUTH_TOKEN = (Get-Content .audit-token -Raw).Trim()
py -m scripts.collect_alter_benchmark --output alter_results.json --limit 20 --confirm-cost
py -m scripts.score_benchmark --input all_results.json --output benchmark_report.json

# Production public/auth boundary smoke
bash scripts/production-e2e.sh

# Read-only capability smoke (requires AUTH_TOKEN; optional providers are marked degraded)
py -m scripts.collect_capability_smoke --output capability_smoke.json

# Stateful reminder/workflow smoke (creates and cleans up a test reminder)
py -m scripts.collect_capability_stateful_smoke --output capability_stateful_smoke.json

# Text + voice latency benchmark (paid; 3 runs = 9 text + 6 voice requests)
py -m scripts.collect_speed_benchmark --output speed_benchmark.json --runs 3 --confirm-cost

# Search quality benchmark (paid; six fresh/local/source scenarios)
py -m scripts.collect_search_benchmark --output search_benchmark.json --confirm-cost
```

Для повторной проверки только провалившихся кейсов можно указать `--case-id` несколько раз, не оплачивая весь suite заново.
