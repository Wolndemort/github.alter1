"""Shared text-chat use case for non-Telegram transports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from config import config
from data.models import ImportantEvent, Session, User
from utils.ap_logic import generate_reply
from utils.vector_memory import recall, remember
from utils.helpers import merge_memory
from utils.memory_facts import extract_user_facts
from utils.weather import get_weather, is_weather_request, parse_weather_city


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

    async def reply(self, db: AsyncSession, user_id: int, text: str) -> ChatResult:
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

        new_facts = extract_user_facts(text)
        if new_facts:
            user.memory = merge_memory(dict(user.memory or {}), new_facts)
            flag_modified(user, "memory")

        events_result = await db.execute(
            select(ImportantEvent).where(ImportantEvent.user_id == user_id)
            .order_by(ImportantEvent.occurred_at.desc()).limit(20)
        )
        memory = dict(user.memory or {})
        events = [{"title": event.title, "event_type": event.event_type,
                   "importance": event.importance, "description": event.description}
                  for event in events_result.scalars()]
        if events:
            memory["important_events"] = events
        if len(text) >= config.MEMORY_AUTO_RECALL_MIN_CHARS:
            recalled = await recall(db, user_id, text)
            if recalled:
                memory["related_previous_context"] = recalled

        if is_weather_request(text):
            city = parse_weather_city(text)
            reply = await get_weather(city) or f"Не удалось получить актуальный прогноз для {city}. Попробуй ещё раз через минуту."
        else:
            reply = await generate_reply(list(session.raw_messages), memory)
        _append(session, "assistant", reply)
        await remember(db, user_id, text, source="user_message")
        await db.commit()
        return ChatResult(reply=reply, session_id=session.id)
