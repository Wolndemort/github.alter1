"""Shared text-chat use case for non-Telegram transports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from config import config
from data.models import ImportantEvent, Reminder, Session, User
from utils.ap_logic import _append_source_links, clear_tool_trace, generate_reply, stream_text_reply, stream_chat_with_tools, tool_trace
from utils.prompts import ALTER_CHARACTER_PROMPT, ALTER_INTELLIGENCE_PROMPT, ALTER_SYSTEM_PROMPT, CHAT_BEHAVIOR_PROMPT, MEMORY_POLICY_PROMPT, PUBLIC_RESPONSE_POLICY, REASONING_POLICY_PROMPT, TOOL_POLICY_PROMPT, RELIABILITY_PROMPT
from utils.capabilities import CAPABILITIES_PROMPT
from utils.vector_memory import recall, remember
from utils.memory_store import merge_memory_facts
from utils.memory_facts import extract_user_facts
from utils.weather import get_weather, is_weather_request, parse_weather_city
from utils.capabilities import capabilities_reply, is_capabilities_request
from utils.calendar_intent import handle_calendar_request
from utils.reminders import is_reminder_request, parse_reminder, parse_time_answer, looks_like_time_answer, extract_reminder_text
from utils.intent import conversation_mode, do_not_remember, explicit_memory_fact, should_recall_context
from utils.quality import sanitize_public_reply
from utils.feedback_memory import feedback_context
from utils.action_log import append_action
from utils.workflow_state import workflow_view
from utils.agent_engine import agent_view
from datetime import timedelta


@dataclass(frozen=True)
class ChatResult:
    reply: str
    session_id: int


def _append(session: Session, role: str, content: str) -> None:
    messages = list(session.raw_messages or [])
    messages.append({"role": role, "content": content, "timestamp": datetime.now(timezone.utc).isoformat()})
    session.raw_messages = messages[-100:]


async def _quality_gated_chunks(streamer, *, chunk_size: int = 96, tool_mode: bool = False, early_stream: bool = False):
    """Gate output while releasing safe ordinary text early."""
    parts = []
    pending = ""
    emitted = False
    async for delta in streamer:
        delta = str(delta or "")
        parts.append(delta)
        if not early_stream or tool_mode:
            continue
        pending += delta
        if len(pending) < 192:
            continue
        candidate, pending = pending[:-96], pending[-96:]
        if sanitize_public_reply(candidate) == candidate:
            emitted = True
            for index in range(0, len(candidate), chunk_size):
                yield candidate[index:index + chunk_size]
    reply = sanitize_public_reply("".join(parts))
    trace = tool_trace()
    if tool_mode:
        reply = _append_source_links(reply, trace)
    # Tool-aware generation is also used for ordinary text to keep its
    # quality consistent with voice/non-streaming replies. Do not add a
    # source footer when the model did not actually call a tool.
    if tool_mode and trace and "http" not in reply.casefold() and "source:" not in reply.casefold() and "источник" not in reply.casefold():
        failed = any(str(item.get("status") or "") != "ok" for item in trace)
        note = "Источник: данные инструмента не получены, актуальные факты не подтверждены." if failed or not trace else "Источник: подключённый инструмент ALTER."
        reply = f"{reply.rstrip()}\n\n{note}"
    if emitted and not tool_mode:
        if pending and sanitize_public_reply(pending) == pending:
            for index in range(0, len(pending), chunk_size):
                yield pending[index:index + chunk_size]
        return
    for index in range(0, len(reply), chunk_size):
        yield reply[index:index + chunk_size]


def validate_message(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        raise ValueError("message cannot be empty")
    if len(value) > config.AI_MAX_PROMPT_CHARS:
        raise ValueError("message is too long")
    return value


def _stream_system_prompt(text: str, memory: dict, *, use_tools: bool = False) -> str:
    """Use a compact policy set for short ordinary messages."""
    if use_tools or len(text) >= 240:
        parts = (
            ALTER_SYSTEM_PROMPT, ALTER_CHARACTER_PROMPT, ALTER_INTELLIGENCE_PROMPT,
            CAPABILITIES_PROMPT, CHAT_BEHAVIOR_PROMPT, TOOL_POLICY_PROMPT,
            MEMORY_POLICY_PROMPT, REASONING_POLICY_PROMPT, PUBLIC_RESPONSE_POLICY, RELIABILITY_PROMPT,
        )
    else:
        parts = (
            ALTER_SYSTEM_PROMPT, ALTER_CHARACTER_PROMPT, ALTER_INTELLIGENCE_PROMPT,
            CHAT_BEHAVIOR_PROMPT, MEMORY_POLICY_PROMPT, PUBLIC_RESPONSE_POLICY, RELIABILITY_PROMPT,
        )
    memory_block = "Релевантная память пользователя:\n<user_memory>\n" + json.dumps(memory, ensure_ascii=False) + "\n</user_memory>"
    # Keep core durable facts in a compact tail so prompt truncation cannot
    # hide identity and family behind episodic context or reminders.
    priority = {
        category: memory[category]
        for category in ("identity", "family", "skills_career")
        if memory.get(category)
    }
    if priority:
        memory_block += (
            "\n\nКлючевые долговременные факты пользователя:\n"
            "<priority_user_memory>\n"
            + json.dumps(priority, ensure_ascii=False)
            + "\n</priority_user_memory>"
        )
    return "\n\n".join((*parts, memory_block))


class ChatService:
    """Coordinates persistence and AI; it has no knowledge of Telegram or HTTP."""

    async def reply(self, db: AsyncSession, user_id: int, text: str, location: dict | None = None) -> ChatResult:
        text = validate_message(text)
        clear_tool_trace()
        user = await db.get(User, user_id)
        if user is None:
            raise ValueError("user not found")
        private_mode = bool((user.tech_stack or {}).get("private_mode"))
        if private_mode:
            session = Session(user_id=user_id, raw_messages=[])
        else:
            result = await db.execute(select(Session).where(
                Session.user_id == user_id,
                Session.is_processed.is_(False),
            ).order_by(Session.started_at.desc()).limit(1))
            session = result.scalar_one_or_none()
            if session is None:
                previous_result = await db.execute(select(Session).where(
                    Session.user_id == user_id,
                ).order_by(Session.started_at.desc()).limit(1))
                previous = previous_result.scalar_one_or_none()
                carried = [
                    {key: item[key] for key in ("role", "content") if key in item}
                    for item in (previous.raw_messages or [])[-40:]
                    if isinstance(item, dict) and item.get("role") in {"user", "assistant"} and item.get("content")
                ] if previous is not None else []
                session = Session(user_id=user_id, raw_messages=carried)
                db.add(session)
                await db.flush()
        _append(session, "user", text)
        pending_reminder = dict(user.pending_reminder or {})
        if pending_reminder and looks_like_time_answer(text):
            remind_at = parse_time_answer(text)
            if remind_at and not private_mode:
                reminder_text = str(pending_reminder.get("text") or "").strip()
                if reminder_text:
                    db.add(Reminder(user_id=user.id, remind_at=remind_at, follow_up_at=remind_at + timedelta(hours=2), text=reminder_text[:500]))
                    user.pending_reminder = {}
                    reply = f"Записал. Напомню {remind_at.strftime('%d.%m в %H:%M')}: {reminder_text}"
                    _append(session, "assistant", reply)
                    await db.commit()
                    return ChatResult(reply=reply, session_id=session.id or 0)
        if is_capabilities_request(text):
            reply = capabilities_reply()
            _append(session, "assistant", reply)
            await db.commit()
            return ChatResult(reply=reply, session_id=session.id or 0)

        ephemeral_request = do_not_remember(text)
        new_facts = {} if ephemeral_request else extract_user_facts(text)
        explicit_fact = None if ephemeral_request else explicit_memory_fact(text)
        if explicit_fact:
            new_facts = dict(new_facts)
            preferences = dict(new_facts.get("preferences") or {})
            explicit_facts = list(preferences.get("explicit_facts") or [])
            if explicit_fact not in explicit_facts:
                explicit_facts.append(explicit_fact)
            preferences["explicit_facts"] = explicit_facts[-20:]
            new_facts["preferences"] = preferences
        if new_facts and not private_mode:
            user.memory = merge_memory_facts(dict(user.memory or {}), new_facts)
            flag_modified(user, "memory")

        events_result = await db.execute(
            select(ImportantEvent).where(ImportantEvent.user_id == user_id)
            .order_by(ImportantEvent.occurred_at.desc()).limit(20)
        )
        reminders_result = await db.execute(
            select(Reminder).where(
                Reminder.user_id == user_id,
                Reminder.is_sent.is_(False),
                Reminder.remind_at >= datetime.now(timezone.utc),
            ).order_by(Reminder.remind_at).limit(12)
        )
        memory = dict(user.memory or {})
        feedback = feedback_context(user.tech_stack)
        if feedback:
            memory["response_feedback"] = feedback
        workflow = workflow_view(user.tech_stack)
        if workflow:
            memory["active_workflow"] = workflow
        agent = agent_view(user.tech_stack)
        if agent:
            memory["active_agent"] = agent
        if isinstance(location, dict):
            memory["current_location"] = {
                key: location[key] for key in ("city", "region", "country", "latitude", "longitude")
                if location.get(key) not in (None, "")
            }
            settings = dict(user.tech_stack or {})
            settings["current_location"] = dict(memory["current_location"])
            user.tech_stack = settings
        events = [{"title": event.title, "event_type": event.event_type,
                   "importance": event.importance, "description": event.description}
                  for event in events_result.scalars()]
        if events:
            memory["important_events"] = events
        active_reminders = [{"text": getattr(item, "text", ""), "remind_at": getattr(getattr(item, "remind_at", None), "isoformat", lambda: "")()} for item in reminders_result.scalars() if getattr(item, "text", None)]
        if active_reminders:
            memory["active_reminders"] = active_reminders
        if should_recall_context(text):
            recalled = await recall(db, user_id, text)
            if recalled:
                # Vector recall is a hint from older conversations, never an
                # authoritative fact. Current explicit memory and the latest
                # user message must win over it when they disagree.
                memory["related_previous_context"] = recalled
                memory["historical_context_policy"] = "These are historical hints; current message and durable memory override conflicts."

        parsed_reminder = parse_reminder(text)
        if parsed_reminder:
            remind_at, reminder_text = parsed_reminder
            if private_mode:
                reply = "В приватном режиме я не сохраняю напоминания. Выключи его, если нужно поставить напоминание."
            else:
                db.add(Reminder(user_id=user.id, remind_at=remind_at,
                                follow_up_at=remind_at + timedelta(hours=2),
                                text=reminder_text[:500]))
                reply = f"Записал. Напомню {remind_at.strftime('%d.%m в %H:%M')}: {reminder_text}"
        elif is_reminder_request(text):
            reminder_text = extract_reminder_text(text)
            if reminder_text:
                user.pending_reminder = {"text": reminder_text[:500]}
                reply = f"Укажи время для напоминания про «{reminder_text}». Например: завтра в 10:00 или через 2 часа."
            else:
                reply = "Что именно напомнить и во сколько?"
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
        reply = sanitize_public_reply(reply)
        if not private_mode:
            _append(session, "assistant", reply)
            if not ephemeral_request:
                await remember(db, user_id, text, source="explicit_memory" if explicit_fact else "user_message", categories=list(new_facts))
            trace = tool_trace()
            append_action(user, "chat", "ok", route=conversation_mode(text), count=len(trace))
            for item in trace:
                append_action(user, "tool", item["status"], tool=item["tool"])
        await db.commit()
        return ChatResult(reply=reply, session_id=session.id or 0)

    async def stream_reply(self, db: AsyncSession, user_id: int, text: str, location: dict | None = None, use_tools: bool = False):
        """Stream ordinary text replies while preserving the same session contract."""
        text = validate_message(text)
        clear_tool_trace()
        user = await db.get(User, user_id)
        if user is None:
            raise ValueError("user not found")
        private_mode = bool((user.tech_stack or {}).get("private_mode"))
        if private_mode:
            session = Session(user_id=user_id, raw_messages=[])
        else:
            result = await db.execute(select(Session).where(
                Session.user_id == user_id, Session.is_processed.is_(False)
            ).order_by(Session.started_at.desc()).limit(1))
            session = result.scalar_one_or_none()
            if session is None:
                previous_result = await db.execute(select(Session).where(
                    Session.user_id == user_id,
                ).order_by(Session.started_at.desc()).limit(1))
                previous = previous_result.scalar_one_or_none()
                carried = [
                    {key: item[key] for key in ("role", "content") if key in item}
                    for item in (previous.raw_messages or [])[-40:]
                    if isinstance(item, dict)
                    and item.get("role") in {"user", "assistant"}
                    and item.get("content")
                ] if previous is not None else []
                session = Session(user_id=user_id, raw_messages=carried)
                db.add(session)
                await db.flush()
        _append(session, "user", text)
        # Capability inventory is deterministic. Do not route this short,
        # well-defined question through a generic streaming model that may
        # answer with a vague "tell me what to do" prompt.
        if is_capabilities_request(text):
            reply = capabilities_reply()
            _append(session, "assistant", reply)
            if not private_mode:
                await db.commit()
            for index in range(0, len(reply), 96):
                yield reply[index:index + 96]
            return
        pending_reminder = dict(user.pending_reminder or {})
        if pending_reminder and looks_like_time_answer(text):
            remind_at = parse_time_answer(text)
            if remind_at and not private_mode:
                reminder_text = str(pending_reminder.get("text") or "").strip()
                if reminder_text:
                    db.add(Reminder(user_id=user.id, remind_at=remind_at, follow_up_at=remind_at + timedelta(hours=2), text=reminder_text[:500]))
                    user.pending_reminder = {}
                    reply = f"Записал. Напомню {remind_at.strftime('%d.%m в %H:%M')}: {reminder_text}"
                    _append(session, "assistant", reply)
                    await db.commit()
                    for index in range(0, len(reply), 96):
                        yield reply[index:index + 96]
                    return
        parsed_reminder = parse_reminder(text)
        if parsed_reminder or is_reminder_request(text):
            if parsed_reminder and not private_mode:
                remind_at, reminder_text = parsed_reminder
                db.add(Reminder(user_id=user.id, remind_at=remind_at,
                                follow_up_at=remind_at + timedelta(hours=2), text=reminder_text[:500]))
                reply = f"Записал. Напомню {remind_at.strftime('%d.%m в %H:%M')}: {reminder_text}"
            elif private_mode:
                reply = "В приватном режиме я не сохраняю напоминания. Выключи его, если нужно поставить напоминание."
            else:
                reminder_text = extract_reminder_text(text)
                if reminder_text:
                    user.pending_reminder = {"text": reminder_text[:500]}
                    reply = f"На какое время поставить напоминание про «{reminder_text}»?"
                else:
                    reply = "Что именно напомнить и когда?"
            _append(session, "assistant", reply)
            await db.commit()
            for index in range(0, len(reply), 96):
                yield reply[index:index + 96]
            return
        ephemeral_request = do_not_remember(text)
        new_facts = {} if ephemeral_request else extract_user_facts(text)
        if new_facts and not private_mode:
            user.memory = merge_memory_facts(dict(user.memory or {}), new_facts)
            flag_modified(user, "memory")
        events_result = await db.execute(
            select(ImportantEvent).where(ImportantEvent.user_id == user_id)
            .order_by(ImportantEvent.occurred_at.desc()).limit(20)
        )
        reminders_result = await db.execute(
            select(Reminder).where(
                Reminder.user_id == user_id,
                Reminder.is_sent.is_(False),
                Reminder.remind_at >= datetime.now(timezone.utc),
            ).order_by(Reminder.remind_at).limit(12)
        )
        memory = dict(user.memory or {})
        feedback = feedback_context(user.tech_stack)
        if feedback:
            memory["response_feedback"] = feedback
        workflow = workflow_view(user.tech_stack)
        if workflow:
            memory["active_workflow"] = workflow
        agent = agent_view(user.tech_stack)
        if agent:
            memory["active_agent"] = agent
        if isinstance(location, dict):
            memory["current_location"] = {key: location[key] for key in ("city", "region", "country") if location.get(key) not in (None, "")}
            settings = dict(user.tech_stack or {})
            settings["current_location"] = dict(memory["current_location"])
            user.tech_stack = settings
        events = [{"title": event.title, "event_type": event.event_type, "description": event.description} for event in events_result.scalars()]
        if events:
            memory["important_events"] = events
        active_reminders = [{"text": getattr(item, "text", ""), "remind_at": getattr(getattr(item, "remind_at", None), "isoformat", lambda: "")()} for item in reminders_result.scalars() if getattr(item, "text", None)]
        if active_reminders:
            memory["active_reminders"] = active_reminders
        if should_recall_context(text):
            recalled = await recall(db, user_id, text)
            if recalled:
                memory["related_previous_context"] = recalled
                memory["historical_context_policy"] = "These are historical hints; current message and durable memory override conflicts."
        # Keep durable memory at the very end of the system message. The
        # upstream prompt guard preserves the tail when the policy is long;
        # placing the mode marker after memory used to cut off identity and
        # family facts, making the model claim it knew nothing about them.
        system = "\nINTERNAL RESPONSE MODE (do not mention it): " + conversation_mode(text) + "\n\n" + _stream_system_prompt(text, memory, use_tools=use_tools)
        working = [{"role": "system", "content": system}, *[{"role": item.get("role"), "content": item.get("content", "")} for item in (session.raw_messages or []) if item.get("role") in {"user", "assistant"}]]
        streamer = stream_chat_with_tools(working) if use_tools else stream_text_reply(working)
        gated_chunks = _quality_gated_chunks(streamer, tool_mode=use_tools, early_stream=not use_tools)
        reply_parts = []
        async for chunk in gated_chunks:
            reply_parts.append(chunk)
            yield chunk
        reply = "".join(reply_parts)
        if not private_mode:
            _append(session, "assistant", reply)
            if not ephemeral_request:
                await remember(db, user_id, text, source="user_message", categories=list(new_facts))
            trace = tool_trace()
            append_action(user, "chat", "ok", route=conversation_mode(text), count=len(trace))
            for item in trace:
                append_action(user, "tool", item["status"], tool=item["tool"])
        await db.commit()
