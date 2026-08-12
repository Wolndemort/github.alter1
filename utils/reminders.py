import re
from datetime import datetime, timedelta, timezone

MOSCOW = timezone(timedelta(hours=3))


def is_reminder_request(text: str) -> bool:
    return bool(re.search(r"\b(?:напомни|поставь\s+напоминание|создай\s+напоминание)\b", (text or "").casefold()))


def extract_reminder_text(text: str) -> str:
    value = re.sub(r"^.*?\b(?:напомни|поставь\s+напоминание|создай\s+напоминание)\b", "", text or "", count=1, flags=re.I)
    return re.sub(r"\s+", " ", value).strip(" ,.!?-")


def parse_reminder(text: str) -> tuple[datetime, str] | None:
    """Parse only unambiguous reminder phrases; return None otherwise."""
    now = datetime.now(MOSCOW)
    match = re.search(r"\b(сегодня|завтра)\s+в\s+(\d{1,2}):(\d{2})\s+(.+)", text.lower())
    if match:
        day = now.date() + timedelta(days=match.group(1) == "завтра")
        hour, minute = int(match.group(2)), int(match.group(3))
        if hour > 23 or minute > 59:
            return None
        remind_at = datetime.combine(day, datetime.min.time(), tzinfo=MOSCOW).replace(hour=hour, minute=minute)
        return (remind_at, match.group(4).strip()) if remind_at > now else None

    match = re.search(r"\bчерез\s+(\d+)\s+(минут(?:у|ы)?|час(?:а|ов)?)\s+(.+)", text.lower())
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        delta = timedelta(minutes=amount) if unit.startswith("минут") else timedelta(hours=amount)
        return now + delta, match.group(3).strip()
    return None


def parse_time_answer(text: str) -> datetime | None:
    now = datetime.now(MOSCOW)
    match = re.search(r"(?:в\s*)?(\d{1,2}):(\d{2})", text.lower())
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
        if hour <= 23 and minute <= 59:
            result = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            return result if result > now else result + timedelta(days=1)
    match = re.search(r"(завтра\s+)?в\s+(\d{1,2})(?!\d|\s*:\d{2})", text.casefold())
    if match:
        hour = int(match.group(2))
        if hour <= 23:
            result = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            if match.group(1):
                result += timedelta(days=1)
            return result if result > now else result + timedelta(days=1)
    # Natural-language answers: «в девять», «завтра в 10».
    match = re.search(r"(?:завтра\s+)?в\s+(один|два|три|четыре|пять|шесть|семь|восемь|девять|десять|одиннадцать|двенадцать)(?:\s+час(?:а|ов)?)?", text.casefold())
    if match:
        hours = {
            "один": 1, "два": 2, "три": 3, "четыре": 4, "пять": 5,
            "шесть": 6, "семь": 7, "восемь": 8, "девять": 9,
            "десять": 10, "одиннадцать": 11, "двенадцать": 12,
        }
        result = now.replace(hour=hours[match.group(1)], minute=0, second=0, microsecond=0)
        if "завтра" in match.group(0):
            result += timedelta(days=1)
        return result if result > now else result + timedelta(days=1)
    match = re.search(r"через\s+(\d+)\s+(минут(?:у|ы)?|час(?:а|ов)?)", text.lower())
    if match:
        amount = int(match.group(1))
        return now + (timedelta(minutes=amount) if match.group(2).startswith("минут") else timedelta(hours=amount))
    return None


def looks_like_time_answer(text: str) -> bool:
    """Return whether a message is intended to answer a reminder time.

    This deliberately stays narrower than ``parse_time_answer``: a pending
    reminder must not hijack an unrelated message in the user's conversation.
    """
    value = (text or "").casefold()
    return bool(
        re.search(r"\b\d{1,2}:\d{2}\b", value)
        or re.search(r"\b(?:через|в|завтра|сегодня)\s+\d{1,2}\b", value)
        or re.search(r"\b(?:через)\s+\d+\s+(?:минут\w*|час\w*)\b", value)
        or re.search(r"\b(?:в|через)\s+(?:один|два|три|четыре|пять|шесть|семь|восемь|девять|десять|одиннадцать|двенадцать)\b", value)
    )


# UTF-8 Russian compatibility layer. The legacy parser above is retained for
# old persisted/test strings, while new users get natural-language parsing.
_legacy_is_reminder_request = is_reminder_request
_legacy_parse_reminder = parse_reminder
_RU_REMINDER_REQUEST = re.compile(r"\b(?:напомни|поставь напоминание|создай напоминание)\b", re.I)
_RU_EXPLICIT_REMINDER = re.compile(r"\b(сегодня|завтра)\s+в\s+(\d{1,2})(?::(\d{2}))?\s+(.+)", re.I)
_RU_RELATIVE_REMINDER = re.compile(r"\bчерез\s+(\d+)\s+(минут(?:у|ы)?|час(?:а|ов)?)\s+(.+)", re.I)


def is_reminder_request(text: str) -> bool:
    return _legacy_is_reminder_request(text) or bool(_RU_REMINDER_REQUEST.search(text or ""))


def parse_reminder(text: str) -> tuple[datetime, str] | None:
    now = datetime.now(MOSCOW)
    match = _RU_EXPLICIT_REMINDER.search(text or "")
    if match:
        day = now.date() + timedelta(days=1 if match.group(1).casefold() == "завтра" else 0)
        hour, minute = int(match.group(2)), int(match.group(3) or 0)
        if hour > 23 or minute > 59:
            return None
        remind_at = datetime.combine(day, datetime.min.time(), tzinfo=MOSCOW).replace(hour=hour, minute=minute)
        return (remind_at, match.group(4).strip()) if remind_at > now else None
    match = _RU_RELATIVE_REMINDER.search(text or "")
    if match:
        amount = int(match.group(1))
        delta = timedelta(minutes=amount) if match.group(2).startswith("минут") else timedelta(hours=amount)
        return now + delta, match.group(3).strip()
    return _legacy_parse_reminder(text)
