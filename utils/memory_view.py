"""Human-facing memory projection shared by Telegram and the mobile API."""
from collections.abc import Mapping

CATEGORY_LABELS = {
    "explicit_fact": "О тебе",
    "identity": "О тебе", "health_sport": "Здоровье и спорт", "food_drinks": "Еда и напитки",
    "skills_career": "Навыки и работа", "education": "Учёба и развитие",
    "interests_hobbies": "Интересы и хобби", "goals_habits": "Цели и привычки",
    "psycho_vibe": "Характер и настроение", "relationships": "Отношения и близкие",
    "family": "Семья", "worldview": "Взгляды и ценности", "politics": "Политические взгляды",
    "preferences": "Предпочтения", "travel": "Путешествия", "finance": "Финансовые планы",
    "important_events": "Важные события", "open_loops": "Незавершённые темы",
}
KEY_LABELS = {"name": "Имя", "age": "Возраст", "city": "Город", "job": "Работа", "vehicle": "Автомобиль", "language": "Язык", "title": "Тема", "description": "Описание", "follow_up_question": "Вопрос для возвращения", "follow_up_at": "Вернуться"}

_HIDDEN_KEYS = {"source", "memory_source", "explicit_fact", "explicit fact", "confidence"}

def _label(key):
    raw = str(key).replace("_", " ").strip()
    return KEY_LABELS.get(str(key), raw[:1].upper() + raw[1:])

def _value(value):
    if isinstance(value, Mapping):
        return "; ".join(f"{_label(k)}: {_value(v)}" for k, v in value.items() if v not in (None, ""))
    if isinstance(value, list):
        return ", ".join(_value(item) for item in value if item not in (None, ""))
    return str(value)

def memory_sections(memory):
    """Return labels and values only; never expose storage keys."""
    sections = []
    for category, facts in (memory or {}).items():
        if not facts:
            continue
        items = ([{"label": _label(k), "value": _value(v)} for k, v in facts.items() if str(k).casefold() not in _HIDDEN_KEYS and v not in (None, "")] if isinstance(facts, Mapping)
                 else [{"label": "", "value": _value(v)} for v in facts if v not in (None, "")] if isinstance(facts, list)
                 else [{"label": "", "value": _value(facts)}])
        if items:
            sections.append({"title": CATEGORY_LABELS.get(str(category), _label(category)), "items": items})
    return sections

def format_memory(memory):
    sections = memory_sections(memory)
    if not sections:
        return "🧠 Пока ALTER ничего важного о тебе не запомнил."
    lines = ["🧠 Что ALTER помнит о тебе:"]
    for section in sections:
        lines.append(f"\n{section['title']}:")
        for item in section["items"]:
            lines.append(f"• {item['label']}: {item['value']}" if item["label"] else f"• {item['value']}")
    return "\n".join(lines)
