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
    "style_clothing": "Стиль и одежда", "music": "Музыка", "films_series": "Фильмы и сериалы", "games": "Игры",
    "social": "Друзья и знакомые", "projects": "Проекты", "books": "Книги", "technology": "Техника",
    "episodic_context": "Контекст прошлых разговоров", "current_context": "Текущий разговор",
}
KEY_LABELS = {"name": "Имя", "age": "Возраст", "city": "Город", "job": "Работа", "vehicle": "Автомобиль", "language": "Язык", "title": "Тема", "description": "Описание", "follow_up_question": "Вопрос для возвращения", "follow_up_at": "Вернуться", "user_message": "Сообщение пользователя", "assistant_message": "Ответ ALTER", "excerpt_content": "Фрагмент контекста", "content": "Содержание"}

_HIDDEN_KEYS = {"source", "memory_source", "explicit_fact", "explicit fact", "confidence"}

def _label(key):
    raw = str(key).replace("_", " ").strip()
    return KEY_LABELS.get(str(key), raw[:1].upper() + raw[1:])

def _value(value):
    if isinstance(value, Mapping):
        return "; ".join(f"{_label(k)}: {_value(v)}" for k, v in value.items() if str(k).casefold() not in _HIDDEN_KEYS and not str(k).startswith("_") and v not in (None, ""))
    if isinstance(value, list):
        return ", ".join(_value(item) for item in value if item not in (None, ""))
    return str(value)

def memory_sections(memory, extra_sections=None):
    """Return labels and values only; never expose storage keys."""
    sections = []
    for category, facts in (memory or {}).items():
        if str(category).startswith("_"):
            continue
        if not facts:
            continue
        items = ([{"label": _label(k), "value": _value(v)} for k, v in facts.items() if str(k).casefold() not in _HIDDEN_KEYS and not str(k).startswith("_") and v not in (None, "")] if isinstance(facts, Mapping)
                 else [{"label": "", "value": _value(v)} for v in facts if v not in (None, "")] if isinstance(facts, list)
                 else [{"label": "", "value": _value(facts)}])
        if items:
            sections.append({"category": str(category), "title": CATEGORY_LABELS.get(str(category), _label(category)), "items": items})
    extras = []
    for section in extra_sections or []:
        if not section.get("items"):
            continue
        extras.append({
            **section,
            "items": [
                {**item, "label": _label(item.get("label")) if item.get("label") else ""}
                for item in section.get("items", [])
                if isinstance(item, Mapping) and str(item.get("label", "")).casefold() not in _HIDDEN_KEYS and not str(item.get("label", "")).startswith("_")
            ],
        })
    return sections + extras

def format_memory(memory, extra_sections=None):
    sections = memory_sections(memory, extra_sections)
    if not sections:
        return "🧠 Пока ALTER ничего важного о тебе не запомнил."
    lines = ["🧠 Что ALTER помнит о тебе:"]
    for section in sections:
        lines.append(f"\n{section['title']}:")
        for item in section["items"]:
            lines.append(f"• {item['label']}: {item['value']}" if item["label"] else f"• {item['value']}")
    return "\n".join(lines)


def memory_audit(memory: dict | None) -> list[dict]:
    """Expose safe provenance controls without exposing storage internals."""
    value = memory if isinstance(memory, Mapping) else {}
    metadata = value.get("_meta") if isinstance(value.get("_meta"), Mapping) else {}
    result = []
    for category, fields in metadata.items():
        if not isinstance(fields, Mapping):
            continue
        for key, entry in fields.items():
            if not isinstance(entry, Mapping):
                continue
            result.append({
                # Keep raw identifiers for confirm API calls. The UI owns
                # presentation labels and must never send translated text
                # back as storage keys.
                "category": str(category),
                "key": str(key),
                "confirmed": bool(entry.get("confirmed", False)),
                "first_seen": entry.get("first_seen"),
                "last_seen": entry.get("last_seen"),
                "replacements": len(entry.get("history") or []),
            })
    return result
