# Capability and media benchmark

Текстовый suite измеряет качество диалога, но не доказывает работу внешних
возможностей. Этот контур проверяется отдельно и делится на контрактные,
mock-интеграционные и production smoke-тесты.

| Контур | Что проверяем | Без внешнего баланса |
|---|---|---|
| Capability discovery | ALTER правильно перечисляет доступные и недоступные функции | да |
| Memory/privacy | memory, forget, private mode, personal-data deletion | да |
| Reminders/workflow | create, clarify, cancel, progress, pause, complete | да |
| Calendar | OAuth/status/list/create/delete и честный disconnected state | да, через mocks |
| Web/YouTube | source attribution, provider error, no fabricated completion | частично |
| Voice/audio | STT, TTS, effects, isolation, speech-to-speech contracts | да, через mocks |
| Images/video | validation, options, job state, cancellation, provider errors | да, через mocks |
| Fal.ai production | real image/video generation | нет, нужен баланс Fal.ai |
| Telegram/mobile | command routing, attachment types, SSE statuses, cancellation | да, через local tests |

## Exit criteria

- capability answer never claims an unavailable provider or completed action;
- every external result has a source or explicit unavailable-source note;
- every media job has `queued/running/completed/failed/cancelled` states;
- provider errors are safe, typed and do not charge twice;
- cancellation is idempotent and scoped to the requesting user;
- Fal.ai generation is tested only after balance is intentionally added.

## Stateful production smoke

Read-only checks:

```powershell
py -3 scripts/collect_capability_smoke.py --output capability_smoke.json
```

The stateful smoke creates a reminder for ten minutes and deletes it
immediately, then checks workflow read access, action log, media capabilities
and calendar status. It never starts a paid media job:

```powershell
py -3 scripts/collect_capability_stateful_smoke.py --output capability_stateful_smoke.json
```

Workflow mutation is opt-in because it changes the account's active workflow:

```powershell
py -3 scripts/collect_capability_stateful_smoke.py --check-workflow-mutation --output capability_stateful_smoke.json
```

## Current baseline

The existing capability/media regression set passes locally. Fal.ai is left in
contract/mock mode until a balance is added; this is expected and is not a
reason to fake a successful generation result.
