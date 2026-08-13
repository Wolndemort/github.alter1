"""Conservative extraction of explicit, durable user facts."""
from __future__ import annotations

import re


def _clean(value: str, limit: int = 160) -> str:
    return re.sub(r"\s+", " ", value).strip(" .,!?:;—-\n\t")[:limit]


def _match(text: str, pattern: str) -> str | None:
    found = re.search(pattern, text, re.I)
    return _clean(found.group("value")) if found else None


def _add(result: dict, category: str, key: str, value: str) -> None:
    if value:
        result.setdefault(category, {})[key] = value


def extract_user_facts(text: str) -> dict:
    value = " ".join(str(text or "").split()).strip()
    if not value or value.endswith("?"):
        return {}
    result: dict = {}
    styles = {
        "concise": r"(?:отвечай|пиши|говори)\s+(?:мне\s+)?(?:короче|кратко|по делу)",
        "detailed": r"(?:отвечай|пиши|говори)\s+(?:мне\s+)?(?:подробнее|развёрнуто|детальнее)",
        "casual": r"(?:без официоза|неформально|как друг|по-простому|попроще)",
        "humorous": r"(?:с юмором|пошути|можно пошутить|повеселее)",
        "direct": r"(?:жёстче|прямее|без смягчения|говори прямо)",
    }
    for name, pattern in styles.items():
        if re.search(pattern, value, re.I):
            result["preferences"] = {"response_style": name}

    patterns = (
        ("identity", "name", r"\b(?:меня зовут|мо[её] имя)\s+(?P<value>[^.!?\n]{2,80})"),
        ("identity", "age", r"\b(?:мне|мой возраст)\s+(?P<value>\d{1,3})\s*(?:лет|года|год)?"),
        ("identity", "city", r"\b(?:я живу в|я из|проживаю в)\s+(?P<value>[^.!?\n]{2,80})"),
        ("identity", "language", r"\b(?:мой родной язык|я говорю на|я изучаю язык)\s+(?P<value>[^.!?\n]{2,80})"),
        ("skills_career", "job", r"\b(?:я работаю|моя работа|моя профессия)\s+(?:в|—|-)??\s*(?P<value>[^.!?\n]{2,120})"),
        ("education", "focus", r"\b(?:я изучаю|я учусь|моя специальность)\s+(?P<value>[^.!?\n]{2,120})"),
        ("goals_habits", "goal", r"\b(?:моя цель|я хочу|планирую|собираюсь)\s+(?P<value>[^.!?\n]{2,140})"),
        ("projects", "current", r"\b(?:я работаю над|мой проект|мы делаем проект)\s+(?P<value>[^.!?\n]{2,140})"),
        ("preferences", "vehicle", r"\b(?:у меня|моя|мой)\s+(?:машина|авто|тачка)\s*(?:это|[-:])?\s*(?P<value>[^.!?\n]{2,120})"),
        ("health_sport", "sport", r"\b(?:я занимаюсь|тренируюсь|хожу на)\s+(?P<value>[^.!?\n]{2,100})"),
        ("food_drinks", "likes", r"\b(?:я люблю есть|моя любимая еда|я пью)\s+(?P<value>[^.!?\n]{2,120})"),
    )
    for category, key, pattern in patterns:
        candidate = _match(value, pattern)
        if candidate:
            _add(result, category, key, candidate)

    preference = _match(value, r"\b(?:мне нравится|я люблю|я предпочитаю|мне по душе)\s+(?P<value>[^.!?\n]{2,140})")
    if preference:
        lower = preference.casefold()
        category, key = "preferences", "likes"
        if re.search(r"одежд|стил|кроссов|костюм|цвет|парфюм|аромат", lower): category, key = "style_clothing", "style"
        elif re.search(r"музык|песн|исполнител", lower): category, key = "music", "likes"
        elif re.search(r"фильм|сериал|кино", lower): category, key = "films_series", "likes"
        elif re.search(r"игр|playstation|xbox", lower): category, key = "games", "likes"
        elif re.search(r"хобби|увлечен", lower): category, key = "interests_hobbies", "hobbies"
        _add(result, category, key, preference)

    avoidance = _match(value, r"\b(?:я не люблю|я не ем|я не пью|мне не нравится|я избегаю|не переношу)\s+(?P<value>[^.!?\n]{2,140})")
    if avoidance:
        _add(result, "food_drinks" if re.search(r"ед|ем|пью|мяс|молок|аллерг|продукт", avoidance, re.I) else "preferences", "avoids", avoidance)

    mood = _match(value, r"\b(?:я чувствую себя|моё настроение|мое настроение)\s+(?P<value>[^.!?\n]{2,100})")
    if mood:
        _add(result, "psycho_vibe", "current_mood", mood)
    return result
