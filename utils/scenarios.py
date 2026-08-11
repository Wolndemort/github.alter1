"""ALTER's named workflows, shared by mobile and Telegram surfaces."""

SCENARIOS = (
    {"id": "my_day", "title": "Разложи мой день", "prompt": "Разложи мой день по приоритетам и дай следующий шаг.", "mode": "planning"},
    {"id": "finish_task", "title": "Доведи дело до результата", "prompt": "Помоги довести моё текущее дело до конкретного результата.", "mode": "planning"},
    {"id": "feelings", "title": "Разберись, что я чувствую", "prompt": "Помоги разобраться, что я сейчас чувствую, без диагнозов и лишних советов.", "mode": "support"},
    {"id": "hard_conversation", "title": "Подготовь меня к разговору", "prompt": "Подготовь меня к важному разговору: цель, риски и первая фраза.", "mode": "planning"},
    {"id": "decision", "title": "Прими решение со мной", "prompt": "Помоги принять решение: варианты, критерии и ближайший шаг.", "mode": "decision"},
    {"id": "project", "title": "Собери всё по проекту", "prompt": "Собери по проекту цели, незавершённые дела, риски и план на неделю.", "mode": "planning"},
    {"id": "important", "title": "Верни меня к тому, что важно", "prompt": "Верни меня к тому, что для меня сейчас важно, учитывая сохранённый контекст.", "mode": "continuation"},
)


def list_scenarios() -> list[dict]:
    return [dict(item) for item in SCENARIOS]
