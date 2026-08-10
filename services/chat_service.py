"""Shared text-chat use case for non-Telegram transports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from config import config
from data.models import ImportantEvent, Reminder, Session, User
from utils.ap_logic import generate_reply
from utils.vector_memory import recall, remember
from utils.helpers import merge_memory
from utils.memory_facts import extract_user_facts
from utils.weather import get_weather, is_weather_request, parse_weather_city
from utils.capabilities import capabilities_reply, is_capabilities_request
from utils.calendar_intent import handle_calendar_request
from utils.reminders import is_reminder_request, parse_reminder, extract_reminder_text
from datetime import timedelta


@dataclass(frozen=True)
class ChatResult:
    reply: str
    session_id: int


def _append(session: Session, role: str, content: str) -> None:
    messages = list(session.raw_messages or [])
    messages.append({"role": role, "content": content, "timestamp": datetime.now(timezone.utc).isoformat()})
    session.raw_messages = messages[-100:]


def validate_message(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        raise ValueError("message cannot be empty")
    if len(value) > config.AI_MAX_PROMPT_CHARS:
        raise ValueError("message is too long")
    return value


class ChatService:
    """Coordinates persistence and AI; it has no knowledge of Telegram or HTTP."""

    async def reply(self, db: AsyncSession, user_id: int, text: str, location: dict | None = None) -> ChatResult:
        text = validate_message(text)
        user = await db.get(User, user_id)
        if user is None:
            raise ValueError("user not found")
        result = await db.execute(select(Session).where(
            Session.user_id == user_id,
            Session.is_processed.is_(False),
        ).order_by(Session.started_at.desc()))
        session = result.scalar_one_or_none()
        if session is None:
            session = Session(user_id=user_id, raw_messages=[])
            db.add(session)
            await db.flush()
        _append(session, "user", text)

        if is_capabilities_request(text):
            reply = capabilities_reply()
            _append(session, "assistant", reply)
            await db.commit()
            return ChatResult(reply=reply, session_id=session.id)

        new_facts = extract_user_facts(text)
        if new_facts:
            user.memory = merge_memory(dict(user.memory or {}), new_facts)
            flag_modified(user, "memory")

        events_result = await db.execute(
            select(ImportantEvent).where(ImportantEvent.user_id == user_id)
            .order_by(ImportantEvent.occurred_at.desc()).limit(20)
        )
        memory = dict(user.memory or {})
        if isinstance(location, dict):
            memory["current_location"] = {
                key: location[key] for key in ("city", "region", "country", "latitude", "longitude")
                if location.get(key) not in (None, "")
            }
        events = [{"title": event.title, "event_type": event.event_type,
                   "importance": event.importance, "description": event.description}
                  for event in events_result.scalars()]
        if events:
            memory["important_events"] = events
        if len(text) >= config.MEMORY_AUTO_RECALL_MIN_CHARS:
            recalled = await recall(db, user_id, text)
            if recalled:
                memory["related_previous_context"] = recalled

        parsed_reminder = parse_reminder(text)
        if parsed_reminder:
            remind_at, reminder_text = parsed_reminder
            db.add(Reminder(user_id=user.id, remind_at=remind_at,
                            follow_up_at=remind_at + timedelta(hours=2),
                            text=reminder_text[:500]))
            reply = f"Записал. Напомню {remind_at.strftime('%d.%m в %H:%M')}: {reminder_text}"
        elif is_reminder_request(text):
            reminder_text = extract_reminder_text(text)
            reply = ("Что именно напомнить и во сколько?" if not reminder_text else
                     f"Укажи время для напоминания про «{reminder_text}». Например: завтра в 10:00 или через 2 часа.")
        else:
            reply = None

        health_words = ("здоров", "самочувств", "болит", "температур", "давлен", "кашел", "боль")
        if reply is None and user.checkins_enabled and any(word in text.casefold() for word in health_words):
            followup_at = datetime.now(timezone.utc) + timedelta(hours=4)
            db.add(Reminder(user_id=user.id, kind="health_checkin",
                            remind_at=followup_at, follow_up_at=followup_at + timedelta(hours=2),
                            text="Как ты себя чувствуешь после разговора о здоровье?"))

        calendar_reply = await handle_calendar_request(text, user) if reply is None else None
        if reply is not None:
            pass
        elif calendar_reply is not None:
            reply = calendar_reply
        elif is_weather_request(text):
            city = parse_weather_city(text)
            if not city and isinstance(location, dict):
                city = str(location.get("city") or location.get("region") or "").strip()
            reply = await get_weather(city) or f"Не удалось получить актуальный прогноз для {city}. Попробуй ещё раз через минуту."
        else:
            reply = await generate_reply(list(session.raw_messages), memory)
        _append(session, "assistant", reply)
        await remember(db, user_id, text, source="user_message")
        await db.commit()
        return ChatResult(reply=reply, session_id=session.id)
