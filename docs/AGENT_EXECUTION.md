# Durable agent execution

ALTER's agent is a persisted task graph, not a fixed weekly scenario. The same
engine supports a short task, a diet, a study plan, a project or a multi-week
goal.

## Lifecycle

`goal → tasks → dependencies → claim → tool execution → result → verify/replan`

Tasks have `pending`, `in_progress`, `done` and `blocked` states, priorities,
deadlines, dependencies, attempts and results. A blocked graph never spins;
it waits for an explicit replan.

## API

All routes require the normal bearer token:

```http
POST /api/v1/agent/start
Content-Type: application/json
```

Example:

```json
{
  "goal": "Подготовить план питания на неделю",
  "horizon_minutes": 10080,
  "autonomy_enabled": true,
  "check_interval_minutes": 60,
  "constraints": {"budget_rub": 12000, "allow_external_actions": false},
  "tasks": [
    {"id": "goals", "title": "Определить калории и ограничения", "priority": 1},
    {"id": "menu", "title": "Составить меню", "depends_on": ["goals"]},
    {"id": "shopping", "title": "Собрать список покупок", "depends_on": ["menu"]}
  ]
}
```

Routes:

- `GET /api/v1/agent` — current state and next ready task;
- `POST /api/v1/agent/next` — manually claim one task;
- `POST /api/v1/agent/run` with `{"max_steps": 1}` — execute tasks through the model/tool loop;
- `POST /api/v1/agent/task` with `task_id`, `status=done|blocked` and `result`/`reason`;
- `POST /api/v1/agent/replan` with a replacement `tasks` list;
- `autonomy_enabled=true` opts into one bounded background tick per interval.

An agent plan accepts up to 64 tasks. A single run request is bounded to 8
steps for safety; a 64-step plan continues through successive run requests or
scheduler ticks. Every task records its status, attempt count and result.

Autonomy is off by default. External side effects such as creating reminders
or Calendar events additionally require `constraints.allow_external_actions`.

## Agent tools

The executor can use web search, weather, memory recall, active reminders and
Google Calendar. Search/read tools are safe by default; reminder/calendar
creation is approval-gated by the constraint above. Vision remains a media
input pipeline: images and sampled video frames are sent to the vision model,
and video audio is transcribed and supplied as additional context.

Documents can be sent to `POST /api/v1/chat/document` as multipart `file` plus
an optional `prompt`. Add `agent=true` and optionally `horizon_minutes` to
automatically create an active document agent with extraction, fact-check,
action and verification tasks. TXT, Markdown, CSV and JSON work without extra services;
PDF and DOCX extraction is bounded to 25 MB and 120,000 characters. The
document is passed to the same chat/session pipeline, so the agent can turn it
into tasks or a plan in the next message.

## Local verification

No provider credits are needed for the state/executor benchmark:

```powershell
py -3 -m pytest -q
py -3 scripts/benchmark_agent.py --output agent_benchmark_local.json --runs 1000
py -3 -m compileall -q .
git diff --check
```

The paid text/voice/search benchmarks remain separate and require the explicit
`--confirm-cost` flag.

## Document export

`POST /api/v1/chat/document/edit` accepts multipart `file` and `instruction`.
Instructions use auditable replacements, one per line: `old text => new text`.
The endpoint returns the edited TXT, Markdown, CSV, JSON, or DOCX as a download.
Searchable text-layer PDFs are edited with coordinate-aware replacements and
returned as binary downloads while preserving the surrounding page layout.
Scanned PDFs without a text layer are rejected safely and require OCR first.

Successful document edits are stored as short-lived owner-scoped artifacts.
The response includes `X-ALTER-Artifact-ID`, which can be downloaded with
`GET /api/v1/artifacts/{artifact_id}` using the same bearer token.

For image scans, the optional local OCR adapter uses Pillow and Tesseract. If
the native Tesseract binary is absent, the request remains safe and should use
the hosted vision path instead.

## Unified attachments

`services.attachment_pipeline.prepare_attachment` classifies an attachment as
document, image, video, or audio. Documents produce bounded text plus a
structured profile for the agent; images may add local OCR and otherwise keep a
vision fallback; video and audio remain on their existing frame/transcription
pipelines. No paid provider is called by this preparation step.
