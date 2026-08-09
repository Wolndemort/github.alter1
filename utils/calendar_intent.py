"""Natural-language calendar commands shared by text and voice adapters."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from services import google_calendar

MOSCOW = timezone(timedelta(hours=3))


def _datetime_pair(text: str):
    match = re.search(r"(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2})(?:\s+(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2}))?", text)
    if match:
        start = datetime.strptime(f"{match.group(1)} {match.group(2)}", "%Y-%m-%d %H:%M").replace(tzinfo=MOSCOW)
        end = datetime.strptime(f"{match.group(3) or match.group(1)} {match.group(4) or (start + timedelta(hours=1)).strftime('%H:%M')}", "%Y-%m-%d %H:%M").replace(tzinfo=MOSCOW)
        return start, end
    match = re.search(r"\b(сегодня|завтра)\s+в\s+(\d{1,2})(?::(\d{2}))?", text.casefold())
    if match:
        day = datetime.now(MOSCOW).date() + timedelta(days=1 if match.group(1) == "завтра" else 0)
        start = datetime.combine(day, datetime.min.time(), tzinfo=MOSCOW).replace(hour=int(match.group(2)), minute=int(match.group(3) or 0))
        return start, start + timedelta(hours=1)
    return None


def is_calendar_request(text: str) -> bool:
    value = (text or "").casefold()
    if any(word in value for word in (
        "расписани", "запланируй", "запланировать", "перенеси", "перенести",
        "отмени встреч", "отменить встреч",
    )):
        return True
    return any(word in value for word in ("календар", "встреч", "созвон", "событи"))


async def handle_calendar_request(text: str, user) -> str | None:
    if not is_calendar_request(text):
        return None
    value = text.casefold()
    try:
        if any(word in value for word in ("подключ", "авторизац", "соедини")):
            return "Открой ссылку для подключения Google Calendar:\n\n" + google_calendar.authorization_url(user.id)
        if any(word in value for word in ("статус", "подключен ли", "подключён ли")):
            connected = bool(google_calendar.token_data(user))
            return "Google Calendar подключён." if connected else "Google Calendar пока не подключён. Скажи: подключи Google Calendar."
        if "календар" in value and any(word in value for word in ("список", "какие", "мои календари")):
            calendars = await google_calendar.list_calendars(user)
            if not calendars: return "Доступных календарей не найдено."
            return "Доступные календари:\n" + "\n".join(f"• {item.get('id', '')}: {item.get('summary', item.get('description', 'Без названия'))}" for item in calendars[:20])
        if any(word in value for word in ("покажи", "какие", "что у меня", "список", "календарь на")) and not any(word in value for word in ("добавь", "создай", "запиши")):
            events = await google_calendar.list_events(user)
            if not events: return "На ближайшее время событий нет."
            return "Ближайшие события:\n" + "\n".join(f"• {item.get('id', '')}: {item.get('start', {}).get('dateTime') or item.get('start', {}).get('date', '')} — {item.get('summary', 'Без названия')}" for item in events[:10])
        if any(word in value for word in ("добавь", "создай", "запиши", "поставь")):
            pair = _datetime_pair(text)
            if not pair:
                return "Назови дату и время, например: добавь встречу завтра в 10:00 или 2026-08-20 10:00 встреча."
            start, end = pair
            title = re.sub(r"\d{4}-\d{2}-\d{2}|\d{1,2}:\d{2}|сегодня|завтра|в\s+\d{1,2}(?::\d{2})?|добавь|создай|запиши|поставь|встречу|событие|созвон", " ", text, flags=re.IGNORECASE)
            title = " ".join(title.split()).strip(" ,:.-") or "Встреча"
            event = {"summary": title, "start": {"dateTime": start.isoformat()}, "end": {"dateTime": end.isoformat()}}
            created = await google_calendar.create_event(user, event)
            return f"Добавил в Google Calendar: {created.get('summary', title)}."
        delete_match = re.search(r"(?:удали|отмени).*?(?:событие\s+)?([\w-]{5,})", text, re.IGNORECASE)
        if delete_match:
            await google_calendar.delete_event(user, delete_match.group(1))
            return "Событие удалено из Google Calendar."
        return "С календарём можно: подключить его, показать события, добавить встречу или удалить событие."
    except Exception:
        return "Не удалось обратиться к Google Calendar. Проверь подключение командой /calendar_connect."
