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

    # Communication preferences are durable and high-signal: unlike a mood,
    # they should shape future replies until the user changes them.
    style_patterns = (
        ("concise", r"(?:отвечай|пиши|говори)\s+(?:мне\s+)?(?:короче|кратко|по делу)"),
        ("detailed", r"(?:отвечай|пиши|говори)\s+(?:мне\s+)?(?:подробнее|развёрнуто|детальнее)"),
        ("casual", r"(?:без официоза|неформально|как друг|по-простому|попроще)"),
        ("humorous", r"(?:с юмором|пошути|можно пошутить|повеселее)"),
        ("direct", r"(?:жёстче|прямее|без смягчения|говори прямо)"),
    )
    styles = [name for name, pattern in style_patterns if re.search(pattern, value, re.I)]
    if styles:
        result["preferences"] = {"response_style": styles[-1]}

    patterns = (
        ("identity", "name", r"\b(?:меня зовут|мо[её] имя)\s+(?P<value>[^.!?\n]{2,80})"),
        ("identity", "age", r"\b(?:мне|мой возраст)\s+(?P<value>\d{1,3})\s*(?:лет|года|год)?"),
        ("identity", "city", r"\b(?:я живу в|я из|проживаю в)\s+(?P<value>[^.!?\n]{2,80})"),
        ("identity", "language", r"\b(?:мой родной язык|я говорю на|я изучаю язык)\s+(?P<value>[^.!?\n]{2,80})"),
        ("skills_career", "job", r"\b(?:я работаю|моя работа|моя профессия)\s+(?:в|—|-)?\s*(?P<value>[^.!?\n]{2,120})"),
        ("education", "focus", r"\b(?:я изучаю|я учусь|мо[яю] специальност[ьи])\s+(?P<value>[^.!?\n]{2,120})"),
        ("goals_habits", "goal", r"\b(?:моя цель|я хочу|планирую|собираюсь)\s+(?P<value>[^.!?\n]{2,140})"),
        ("family", "family", r"\b(?:у меня есть|в моей семье)\s+(?!(?:друзья|знакомые|коллеги))(?P<value>[^.!?\n]{2,120})"),
        ("social", "friends", r"\b(?:мои друзья|у меня есть друзья|мой друг|моя подруга|мои знакомые)\s*(?P<value>[^.!?\n]{0,120})"),
        ("social", "colleagues", r"\b(?:мои коллеги|я работаю с коллегами|у меня на работе)\s*(?P<value>[^.!?\n]{0,120})"),
        ("relationships", "relationship", r"\b(?:я встречаюсь|я женат|я замужем|у меня отношения)\s*(?P<value>[^.!?\n]{0,100})"),
        ("skills_career", "skills", r"\b(?:я умею|мои навыки|у меня есть навык|я владею)\s+(?P<value>[^.!?\n]{2,140})"),
        ("projects", "current", r"\b(?:я работаю над|мой проект|мы делаем проект)\s+(?P<value>[^.!?\n]{2,140})"),
        ("travel", "places", r"\b(?:я был в|я ездил в|я путешествовал по|моя любимая страна|хочу поехать в)\s+(?P<value>[^.!?\n]{2,120})"),
        ("books", "likes", r"\b(?:я читаю|моя любимая книга|мне нравятся книги)\s+(?P<value>[^.!?\n]{2,120})"),
        ("food_drinks", "likes", r"\b(?:я люблю есть|я не ем|моя любимая еда|я пью)\s+(?P<value>[^.!?\n]{2,120})"),
        ("worldview", "religion", r"\b(?:я|моя религия|я исповедую)\s+(?P<value>(?:верующий|атеист|православн\w*|мусульман\w*|христиан\w*|ислам|буддизм)[^.!?\n]{0,80})"),
        ("worldview", "values", r"\b(?:для меня важно|мои ценности|я ценю)\s+(?P<value>[^.!?\n]{2,140})"),
        ("finance", "situation", r"\b(?:моя финансовая ситуация|я зарабатываю|мой доход|я коплю на|мои финансовые цели)\s+(?P<value>[^.!?\n]{2,140})"),
        ("technology", "devices", r"\b(?:у меня есть|я пользуюсь|мой телефон|мой ноутбук|мой компьютер)\s+(?P<value>(?:айфон|iphone|android|телефон|ноутбук|компьютер|macbook|playstation|xbox)[^.!?\n]{0,100})"),
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

    avoidance = _match(value, r"\b(?:я не люблю|я не ем|я не пью|мне не нравится|я избегаю|не переношу)\s+(?P<value>[^.!?\n]{2,140})")
    if avoidance:
        lower = avoidance.casefold()
        category, key = "preferences", "dislikes"
        if re.search(r"еда|ем|пью|мяс|молок|аллерг|продукт", lower):
            category, key = "food_drinks", "avoids"
        elif re.search(r"одежд|стиль|цвет", lower):
            category, key = "style_clothing", "avoids"
        _add(result, category, key, avoidance)
        if category == "food_drinks":
            result.get("food_drinks", {}).pop("likes", None)

    mood = _match(value, r"\b(?:я чувствую себя|моё настроение|мое настроение)\s+(?P<value>[^.!?\n]{2,100})")
    if mood:
        _add(result, "psycho_vibe", "current_mood", mood)

    # Explicit plans/events are useful later but remain separate from stable
    # identity facts so they can be expired or converted into reminders.
    event = _match(value, r"\b(?:у меня|мне предстоит|я иду на|я еду на)\s+(?P<value>(?:экзамен|собеседование|операци[яю]|поездк[ау]|встречу|концерт|день рождения)[^.!?\n]{0,120})")
    if event:
        _add(result, "important_events", "current", event)
    return result
