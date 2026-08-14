"""Russian reminder intent and time parsing shared by mobile and Telegram."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone


MOSCOW = timezone(timedelta(hours=3))
_WEEKDAYS = {
    "понедельник": 0, "вторник": 1, "среду": 2, "среда": 2,
    "четверг": 3, "пятницу": 4, "пятница": 4, "субботу": 5,
    "суббота": 5, "воскресенье": 6,
}
_MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
    "мая": 5, "июня": 6, "июля": 7, "августа": 8,
    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}
_NUMBER_HOURS = {
    "один": 1, "два": 2, "три": 3, "четыре": 4, "пять": 5,
    "шесть": 6, "семь": 7, "восемь": 8, "девять": 9,
    "десять": 10, "одиннадцать": 11, "двенадцать": 12,
}
_TRIGGER = re.compile(
    r"\b(?:напомни(?:ть)?|поставь\s+напоминание|создай\s+напоминание)\b",
    re.I,
)
_RELATIVE = re.compile(
    r"\bчерез\s+(?P<amount>\d+)\s+(?P<unit>минут\w*|час\w*|дн(?:я|ей)?|недел\w*)",
    re.I,
)
_CLOCK = r"(?:в|на)\s*(?P<hour>\d{1,2})(?:[:.](?P<minute>\d{2}))?\s*(?P<part>утра|дня|вечера|ночи)?"
_DAY_CLOCK = re.compile(
    rf"\b(?:(?P<day>сегодня|завтра|послезавтра)\s+)?(?P<clock>{_CLOCK})",
    re.I,
)
_WEEKDAY_CLOCK = re.compile(
    rf"\b(?:в\s+)?(?P<weekday>{'|'.join(_WEEKDAYS)})\s+(?P<clock>{_CLOCK})",
    re.I,
)
_DATE_CLOCK = re.compile(
    rf"\b(?P<date_day>\d{{1,2}})\s+(?P<month>{'|'.join(_MONTHS)})\s+(?P<clock>{_CLOCK})",
    re.I,
)


def is_reminder_request(text: str) -> bool:
    return bool(_TRIGGER.search(text or ""))


def _clean_task(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "").strip(" ,.!?-—:;\n\t")
    # These are command fillers, not part of the reminder itself.
    while True:
        cleaned = re.sub(
            r"^(?:мне|пожалуйста|про|об|о|что|чтобы|на|и)\b\s*[,!:;—-]?\s*",
            "",
            value,
            flags=re.I,
        ).strip(" ,.!?-—:;\n\t")
        if cleaned == value:
            return cleaned[:500]
        value = cleaned


def extract_reminder_text(text: str) -> str:
    """Extract only the task, excluding trigger words and time expressions."""
    value = str(text or "")
    match = _TRIGGER.search(value)
    if match:
        value = value[match.end():]
    return _clean_task(value)


def _clock_value(match: re.Match) -> tuple[int, int] | None:
    hour = int(match.group("hour"))
    minute = int(match.group("minute") or 0)
    if hour > 23 or minute > 59:
        return None
    part = (match.group("part") or "").casefold()
    if part in {"утра", "дня", "вечера", "ночи"}:
        if part == "утра" and hour == 12:
            hour = 0
        elif part == "вечера" and hour < 12:
            hour += 12
        elif part == "ночи" and hour == 12:
            hour = 0
    return hour, minute


def _with_clock(day, clock: tuple[int, int], now: datetime, *, rollover: bool = False) -> datetime:
    result = datetime.combine(day, datetime.min.time(), tzinfo=MOSCOW).replace(hour=clock[0], minute=clock[1])
    if rollover and result <= now:
        result += timedelta(days=1)
    return result


def _remove_time(value: str, match: re.Match) -> str:
    return extract_reminder_text(value[:match.start()] + " " + value[match.end():])


def parse_reminder(text: str) -> tuple[datetime, str] | None:
    """Return (future Moscow time, clean task) for an unambiguous request."""
    value = str(text or "")
    now = datetime.now(MOSCOW)

    relative = _RELATIVE.search(value)
    if relative:
        amount = int(relative.group("amount"))
        unit = relative.group("unit").casefold()
        if unit.startswith("минут"):
            delta = timedelta(minutes=amount)
        elif unit.startswith("час"):
            delta = timedelta(hours=amount)
        elif unit.startswith("дн"):
            delta = timedelta(days=amount)
        else:
            delta = timedelta(weeks=amount)
        task = _remove_time(value, relative)
        return now + delta, task if task else extract_reminder_text(value)

    for pattern in (_DATE_CLOCK, _WEEKDAY_CLOCK, _DAY_CLOCK):
        match = pattern.search(value)
        if not match:
            continue
        clock_match = re.search(_CLOCK, match.group("clock"), re.I)
        clock = _clock_value(clock_match) if clock_match else None
        if clock is None:
            return None
        if pattern is _DATE_CLOCK:
            day = int(match.group("date_day"))
            month = _MONTHS[match.group("month").casefold()]
            year = now.year
            try:
                candidate = _with_clock(datetime(year, month, day).date(), clock, now)
            except ValueError:
                return None
            if candidate <= now:
                candidate = candidate.replace(year=year + 1)
        elif pattern is _WEEKDAY_CLOCK:
            target = _WEEKDAYS[match.group("weekday").casefold()]
            days = (target - now.weekday()) % 7 or 7
            candidate = _with_clock((now + timedelta(days=days)).date(), clock, now)
        else:
            day_name = (match.group("day") or "").casefold()
            offset = {"сегодня": 0, "завтра": 1, "послезавтра": 2}.get(day_name)
            candidate = _with_clock(now.date() + timedelta(days=offset or 0), clock, now, rollover=offset is None)
            if offset is not None and candidate <= now:
                return None
        task = _remove_time(value, match)
        return candidate, task if task else extract_reminder_text(value)
    return None


def parse_time_answer(text: str) -> datetime | None:
    """Parse a follow-up answer containing only a reminder time."""
    value = str(text or "")
    now = datetime.now(MOSCOW)
    relative = _RELATIVE.search(value)
    if relative:
        amount = int(relative.group("amount"))
        unit = relative.group("unit").casefold()
        if unit.startswith("минут"):
            return now + timedelta(minutes=amount)
        if unit.startswith("час"):
            return now + timedelta(hours=amount)
        if unit.startswith("дн"):
            return now + timedelta(days=amount)
        return now + timedelta(weeks=amount)
    words = re.search(r"\b(?:(?P<day>завтра|послезавтра)\s+)?в\s+(?P<hour>" + "|".join(_NUMBER_HOURS) + r")\b", value, re.I)
    if words:
        hour = _NUMBER_HOURS[words.group("hour").casefold()]
        offset = {"завтра": 1, "послезавтра": 2}.get((words.group("day") or "").casefold(), 0)
        return _with_clock(now.date() + timedelta(days=offset), (hour, 0), now, rollover=not offset)
    match = re.search(rf"\b(?:(?P<day>завтра|послезавтра)\s+)?(?P<clock>{_CLOCK})", value, re.I)
    if not match:
        match = re.search(r"\b(?:в\s*)?(?P<hour>\d{1,2})[:.](?P<minute>\d{2})\b", value, re.I)
        if not match:
            return None
        clock = _clock_value(match)
        if clock is None:
            return None
        return _with_clock(now.date(), clock, now, rollover=True)
    clock_match = re.search(_CLOCK, match.group("clock"), re.I)
    clock = _clock_value(clock_match) if clock_match else None
    if clock is None:
        return None
    offset = {"завтра": 1, "послезавтра": 2}.get((match.group("day") or "").casefold(), 0)
    return _with_clock(now.date() + timedelta(days=offset), clock, now, rollover=not offset)


def looks_like_time_answer(text: str) -> bool:
    value = (text or "").casefold()
    return bool(
        re.search(r"\b\d{1,2}[:.]\d{2}\b", value)
        or re.search(r"\b(?:через|в|на|завтра|послезавтра|сегодня)\s+\d{1,2}\b", value)
        or _RELATIVE.search(value)
        or re.search(r"\b(?:в|через)\s+(?:один|два|три|четыре|пять|шесть|семь|восемь|девять|десять|одиннадцать|двенадцать)\b", value)
    )
