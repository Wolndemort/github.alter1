import re
from datetime import datetime, timedelta, timezone

MOSCOW = timezone(timedelta(hours=3))


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
    match = re.search(r"через\s+(\d+)\s+(минут(?:у|ы)?|час(?:а|ов)?)", text.lower())
    if match:
        amount = int(match.group(1))
        return now + (timedelta(minutes=amount) if match.group(2).startswith("минут") else timedelta(hours=amount))
    return None
