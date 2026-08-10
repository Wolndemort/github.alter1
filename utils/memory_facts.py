"""Conservative, provider-independent extraction of durable user facts.

This runs on every message. It intentionally prefers a small false-negative
rate over filling the user's memory with guesses or facts about other people.
The slower session summarizer remains responsible for complex open loops.
"""
from __future__ import annotations

import re


def _clean(value: str, limit: int = 160) -> str:
    return re.sub(r"\s+", " ", value).strip(" .,!?:;—-\n\t")[:limit]


def _match(text: str, pattern: str) -> str | None:
    found = re.search(pattern, text, re.I)
    return _clean(found.group("value")) if found else None


def _add(result: dict, category: str, key: str, value: str) -> None:
    if not value:
        return
    result.setdefault(category, {})[key] = value


def extract_user_facts(text: str) -> dict:
    """Return high-confidence facts explicitly stated about the user.

    The output keeps the legacy ``category -> fields`` contract used by the
    existing JSONB memory and API. Questions, advice, and third-person facts
    are deliberately ignored.
    """
    value = " ".join(str(text or "").split()).strip()
    if not value or value.endswith("?"):
        return {}
    result: dict = {}

    patterns = (
        ("identity", "name", r"\b(?:меня зовут|мо[её] имя)\s+(?P<value>[^.!?\n]{2,80})"),
        ("identity", "city", r"\b(?:я живу в|я из|проживаю в)\s+(?P<value>[^.!?\n]{2,80})"),
        ("skills_career", "job", r"\b(?:я работаю|моя работа|моя профессия)\s+(?:в|—|-)?\s*(?P<value>[^.!?\n]{2,120})"),
        ("education", "focus", r"\b(?:я изучаю|я учусь|мо[яю] специальност[ьи])\s+(?P<value>[^.!?\n]{2,120})"),
        ("goals_habits", "goal", r"\b(?:моя цель|я хочу|планирую|собираюсь)\s+(?P<value>[^.!?\n]{2,140})"),
        ("family", "family", r"\b(?:у меня есть|в моей семье)\s+(?P<value>[^.!?\n]{2,120})"),
        ("relationships", "relationship", r"\b(?:я встречаюсь|я женат|я замужем|у меня отношения)\s*(?P<value>[^.!?\n]{0,100})"),
        ("preferences", "vehicle", r"\b(?:у меня|моя|мой)\s+(?:машина|авто|тачка)\s*(?:это|[-:])?\s*(?P<value>[^.!?\n]{2,120})"),
        ("health_sport", "health", r"\b(?:у меня|я страдаю от|мне поставили)\s+(?P<value>(?:аллергия|астма|диабет|мигрень|бессонница|давление)[^.!?\n]{0,100})"),
        ("health_sport", "sport", r"\b(?:я занимаюсь|тренируюсь|хожу на)\s+(?P<value>(?:спортом|бегом|плаванием|фитнесом|йогой|борьбой|теннисом|футболом)[^.!?\n]{0,80})"),
    )
    for category, key, pattern in patterns:
        candidate = _match(value, pattern)
        if candidate:
            _add(result, category, key, candidate)

    # Preference statements are classified by their object, not blindly put
    # into one generic bucket. This covers natural phrases like "люблю кино".
    preference = _match(value, r"\b(?:мне нравится|я люблю|я предпочитаю|мне по душе)\s+(?P<value>[^.!?\n]{2,140})")
    if preference:
        lower = preference.casefold()
        category = "preferences"
        key = "likes"
        if re.search(r"одежд|стил|кроссов|костюм|цвет", lower): category, key = "style_clothing", "style"
        elif re.search(r"парфюм|дух|аромат", lower): category, key = "style_clothing", "perfume"
        elif re.search(r"музык|песн|исполнител", lower): category, key = "music", "likes"
        elif re.search(r"фильм|сериал|кино", lower): category, key = "films_series", "likes"
        elif re.search(r"игр|поиграть|playstation|xbox", lower): category, key = "games", "likes"
        elif re.search(r"хобби|увлечен", lower): category, key = "interests_hobbies", "hobbies"
        _add(result, category, key, preference)

    mood = _match(value, r"\b(?:я чувствую себя|моё настроение|мое настроение)\s+(?P<value>[^.!?\n]{2,100})")
    if mood:
        _add(result, "psycho_vibe", "current_mood", mood)

    # Explicit plans/events are useful later but remain separate from stable
    # identity facts so they can be expired or converted into reminders.
    event = _match(value, r"\b(?:у меня|мне предстоит|я иду на|я еду на)\s+(?P<value>(?:экзамен|собеседование|операци[яю]|поездк[ау]|встречу|концерт|день рождения)[^.!?\n]{0,120})")
    if event:
        _add(result, "important_events", "current", event)
    return result
