"""Shared text-chat use case for non-Telegram transports."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from config import config
from data.models import ImportantEvent, Reminder, Session, User
from utils.ap_logic import (_append_source_links, clear_tool_trace,
                            chat_with_fallback, generate_reply, recent_conversation_messages,
                            stream_text_reply, stream_chat_with_tools,
                            summarize_active_context, tool_trace)
from utils.prompts import ALTER_CHARACTER_PROMPT, ALTER_INTELLIGENCE_PROMPT, ALTER_SYSTEM_PROMPT, CHAT_BEHAVIOR_PROMPT, MEMORY_POLICY_PROMPT, PUBLIC_RESPONSE_POLICY, REASONING_POLICY_PROMPT, TOOL_POLICY_PROMPT, RELIABILITY_PROMPT
from utils.capabilities import CAPABILITIES_PROMPT
from utils.vector_memory import recall, remember
from utils.memory_store import merge_memory_facts
from utils.memory_facts import extract_user_facts
from utils.weather import get_weather, is_weather_request, parse_weather_city
from utils.capabilities import capabilities_reply, is_capabilities_request
from utils.calendar_intent import handle_calendar_request
from utils.reminders import is_reminder_request, parse_reminder, parse_time_answer, looks_like_time_answer, extract_reminder_text, pending_reminder_is_fresh
from utils.intent import conversation_mode, do_not_remember, explicit_memory_fact, should_recall_context, should_prefetch_web
from utils.quality import PUBLIC_FALLBACK, has_internal_leak, sanitize_public_reply
from utils.feedback_memory import feedback_context
from utils.action_log import append_action
from utils.workflow_state import workflow_view
from utils.agent_engine import agent_view
from utils.multimodal_context import attachment_context_message
from utils.web_search import search_web
from datetime import timedelta


@dataclass(frozen=True)
class ChatResult:
    reply: str
    session_id: int


def _append(session: Session, role: str, content: str) -> None:
    messages = list(session.raw_messages or [])
    messages.append({"role": role, "content": content, "timestamp": datetime.now(timezone.utc).isoformat()})
    session.raw_messages = messages[-100:]


def _update_conversation_state(session: Session, user_text: str) -> None:
    """Persist deterministic anchors for short follow-ups."""
    state = dict(getattr(session, "conversation_state", None) or {})
    state["last_user_message"] = user_text[:600]
    if session.context_summary:
        state["topic_summary"] = session.context_summary[:1200]
    state["message_count"] = len(session.raw_messages or [])
    session.conversation_state = state


async def _refresh_active_context(session: Session) -> None:
    """Refresh the topic summary only after enough new turns accumulated."""
    messages = [
        item for item in (session.raw_messages or [])
        if isinstance(item, dict) and item.get("role") in {"user", "assistant"} and item.get("content")
    ]
    previous_count = int(getattr(session, "context_summary_messages", 0) or 0)
    if len(messages) < 16 or len(messages) - previous_count < 8:
        return
    source = messages[:-8]
    summary = await summarize_active_context(source, getattr(session, "context_summary", "") or "")
    if summary:
        session.context_summary = summary[:1200]
        session.context_summary_messages = len(messages)


async def record_document_turn(
    db: AsyncSession,
    user_id: int,
    prompt: str,
    reply: str,
    *,
    filename: str,
    media_type: str,
    operation: str,
    artifact_id: str = "",
    observation: str = "",
) -> int:
    """Persist a document turn for every transport using the active chat."""
    result = await db.execute(select(Session).where(
        Session.user_id == user_id,
        Session.is_processed.is_(False),
    ).order_by(Session.started_at.desc()).limit(1))
    session = result.scalar_one_or_none()
    if session is None:
        # Keeps lightweight transport/unit-test database doubles compatible;
        # real AsyncSession always provides add/flush.
        if not hasattr(db, "add") or not hasattr(db, "flush"):
            return 0
        session = Session(user_id=user_id, raw_messages=[])
        db.add(session)
        await db.flush()
    _append(session, "user", validate_message(prompt))
    _append(session, "assistant", sanitize_public_reply(reply))
    _append(session, "assistant", attachment_context_message(
        kind="document", filename=filename, media_type=media_type,
        operation=operation, observation=observation,
        artifact_filename=filename, artifact_media_type=media_type,
        artifact_id=artifact_id,
    ))
    await db.commit()
    return session.id or 0


async def _repair_rejected_stream_reply(raw_reply: str, repair_prompt: str) -> str:
    """Turn a model draft rejected by the gate into a public answer."""
    if raw_reply.strip() == PUBLIC_FALLBACK:
        return PUBLIC_FALLBACK
    try:
        response = await chat_with_fallback(
            [
                {
                    "role": "system",
                    "content": (
                        "Перепиши черновик в готовый ответ пользователю на русском. "
                        "Сохрани смысл и активную тему. Удали внутренний анализ, "
                        "упоминания промптов, правил, инструментов и модели. Верни "
                        "только ответ без пояснений о переписывании."
                    ),
                },
                {
                    "role": "user",
                    "content": f"{repair_prompt}\n\nЧЕРНОВИК:\n{raw_reply[:6000] or '(провайдер не вернул текст)'}",
                },
            ],
            max_tokens=700,
            task="chat",
        )
        repaired = sanitize_public_reply(response.choices[0].message.content or "")
        if repaired != PUBLIC_FALLBACK and not has_internal_leak(repaired):
            return repaired
    except Exception:
        logging.exception("Rejected stream reply repair failed")
    return PUBLIC_FALLBACK


async def _quality_gated_chunks(
    streamer,
    *,
    chunk_size: int = 96,
    tool_mode: bool = False,
    early_stream: bool = False,
    repair_prompt: str = "",
):
    """Gate output while releasing safe ordinary text early."""
    def safe_chunks(value: str):
        # Never make the client render a web answer split inside a word. This
        # is especially noticeable for Russian suffixes in the mobile SSE UI.
        start = 0
        while start < len(value):
            end = min(start + chunk_size, len(value))
            if end < len(value):
                boundary = value.rfind(" ", start, end)
                if boundary > start:
                    end = boundary + 1
            yield value[start:end]
            start = end

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
            for piece in safe_chunks(candidate):
                yield piece
    raw_reply = "".join(parts)
    reply = sanitize_public_reply(raw_reply)
    if (
        repair_prompt
        and raw_reply.strip() != PUBLIC_FALLBACK
        and (reply == PUBLIC_FALLBACK or len(raw_reply.strip()) < 24)
    ):
        reply = await _repair_rejected_stream_reply(raw_reply, repair_prompt)
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
            for piece in safe_chunks(pending):
                yield piece
        return
    for piece in safe_chunks(reply):
        yield piece


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
    # Structured memory is storage, not prompt context. The model receives
    # only semantic retrieval results for the current turn, plus operational
    # state that must always be visible.
    category_names = {"identity", "health_sport", "food_drinks", "skills_career", "education", "interests_hobbies", "goals_habits", "psycho_vibe", "relationships", "family", "social", "projects", "worldview", "politics", "preferences", "style_clothing", "music", "films_series", "games", "travel", "books", "technology", "finance", "important_events", "open_loops"}
    retrieved_memory = {key: value for key, value in memory.items() if key not in category_names}
    memory_block = "Релевантная память пользователя:\n<user_memory>\n" + json.dumps(retrieved_memory, ensure_ascii=False) + "\n</user_memory>"
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
        previous_summary = ""
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
                previous_summary = str(getattr(previous, "summary", "") or "") if previous is not None else ""
                carried = [
                    {key: item[key] for key in ("role", "content") if key in item}
                    for item in (previous.raw_messages or [])[-12:]
                    if isinstance(item, dict) and item.get("role") in {"user", "assistant"} and item.get("content")
                ] if previous is not None else []
                session = Session(
                    user_id=user_id,
                    raw_messages=carried,
                    context_summary=getattr(previous, "context_summary", None) if previous is not None else None,
                    context_summary_messages=len(carried),
                )
                db.add(session)
                await db.flush()
        _append(session, "user", text)
        pending_reminder = dict(user.pending_reminder or {}) if pending_reminder_is_fresh(user.pending_reminder) else {}
        if user.pending_reminder and not pending_reminder:
            user.pending_reminder = {}
        if pending_reminder and looks_like_time_answer(text) and not explicit_memory_fact(text):
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
        await _refresh_active_context(session)
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
        if previous_summary:
            memory["previous_session_summary"] = previous_summary
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
        # Persist the user turn before any embedding/provider call so the
        # database transaction does not stay open while recall is running.
        await db.commit()
        if should_recall_context(text):
            recalled = await recall(db, user_id, text)
            if recalled:
                # Vector recall is a hint from older conversations, never an
                # authoritative fact. Current explicit memory and the latest
                # user message must win over it when they disagree.
                memory["related_previous_context"] = recalled
                memory["historical_context_policy"] = "These are historical hints; current message and durable memory override conflicts."

        if should_prefetch_web(text):
            results = await search_web(text, max_results=6)
            if results:
                memory["web_search_context"] = [
                    {key: item.get(key, "") for key in ("title", "url", "content")}
                    for item in results[:6]
                ]
            else:
                # A factual request without evidence must not be answered with
                # confident guesses by a fallback model.
                memory["web_search_status"] = "requested_but_unavailable"
                memory["web_search_policy"] = "State that the fact could not be verified; do not invent specifics."

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
                user.pending_reminder = {"text": reminder_text[:500], "created_at": datetime.now(timezone.utc).isoformat()}
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

        # Calendar, weather and model providers are external work. Release
        # the transaction before awaiting them; otherwise a slow reply can
        # block session/notification inserts for every other request.
        await db.commit()
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
            recent = recent_conversation_messages(
                session.raw_messages,
                max_turns=6 if session.context_summary else 8,
            )
            if session.context_summary:
                reply = await generate_reply(recent, memory, conversation_summary=session.context_summary)
            else:
                reply = await generate_reply(recent, memory)
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
        previous_summary = ""
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
                previous_summary = str(getattr(previous, "summary", "") or "") if previous is not None else ""
                carried = [
                    {key: item[key] for key in ("role", "content") if key in item}
                    for item in (previous.raw_messages or [])[-12:]
                    if isinstance(item, dict)
                    and item.get("role") in {"user", "assistant"}
                    and item.get("content")
                ] if previous is not None else []
                session = Session(
                    user_id=user_id,
                    raw_messages=carried,
                    context_summary=getattr(previous, "context_summary", None) if previous is not None else None,
                    context_summary_messages=len(carried),
                )
                db.add(session)
                await db.flush()
        _append(session, "user", text)
        await _refresh_active_context(session)
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
        pending_reminder = dict(user.pending_reminder or {}) if pending_reminder_is_fresh(user.pending_reminder) else {}
        if user.pending_reminder and not pending_reminder:
            user.pending_reminder = {}
        if pending_reminder and looks_like_time_answer(text) and not explicit_memory_fact(text):
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
                    user.pending_reminder = {"text": reminder_text[:500], "created_at": datetime.now(timezone.utc).isoformat()}
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
        if previous_summary:
            memory["previous_session_summary"] = previous_summary
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
        # Persist the user turn before any embedding/provider call so the
        # database transaction does not stay open while recall is running.
        await db.commit()
        # Memory retrieval is semantic, not category-driven. Search on every
        # turn so an explicit entity (academy, project, address, etc.) can
        # retrieve the fact even when the user does not say "remember" again.
        recalled = await recall(db, user_id, text)
        if recalled:
            memory["related_previous_context"] = recalled
            memory["historical_context_policy"] = "These are historical hints; current message and durable memory override conflicts."
        if should_prefetch_web(text):
            results = await search_web(text, max_results=6)
            if results:
                memory["web_search_context"] = [
                    {key: item.get(key, "") for key in ("title", "url", "content")}
                    for item in results[:6]
                ]
            else:
                memory["web_search_status"] = "requested_but_unavailable"
                memory["web_search_policy"] = "State that the fact could not be verified; do not invent specifics."
        # Keep durable memory at the very end of the system message. The
        # upstream prompt guard preserves the tail when the policy is long;
        # placing the mode marker after memory used to cut off identity and
        # family facts, making the model claim it knew nothing about them.
        system = "\nINTERNAL RESPONSE MODE (do not mention it): " + conversation_mode(text) + "\n\n" + _stream_system_prompt(text, memory, use_tools=use_tools)
        system += "\n\nREMINDER SAFETY: Never claim to have created, saved, cancelled, or scheduled a reminder unless the user's latest message explicitly asks for that reminder action. A story, plan, reflection, or mention of a date/time is not a reminder request."
        if session.context_summary:
            system += "\n\nACTIVE CONVERSATION SUMMARY (authoritative for the current topic):\n" + session.context_summary[:1200]
        live_state = getattr(session, "conversation_state", None) or {}
        if live_state:
            system += "\n\nSTRUCTURED LIVE CONVERSATION STATE (use to resolve short follow-ups):\n" + json.dumps(live_state, ensure_ascii=False)[:1400]
        working = [
            {"role": "system", "content": system},
            *recent_conversation_messages(
                session.raw_messages,
                max_turns=6 if session.context_summary else 8,
            ),
        ]
        # Do not keep the database transaction open while waiting for an
        # external model/tool response. The stream route owns this session,
        # so an uncommitted session insert here used to remain idle in
        # transaction and block other web requests for the same user.
        await db.commit()
        streamer = stream_chat_with_tools(working) if use_tools else stream_text_reply(working)
        # Hold text until the complete provider response is available. Early
        # prefix streaming exposed half-formed tool/model continuations and
        # made mobile render semantic fragments before the quality gate ran.
        repair_prompt = (
            "ТЕКУЩИЙ ЗАПРОС ПОЛЬЗОВАТЕЛЯ:\n" + text +
            ("\n\nАКТИВНАЯ ТЕМА:\n" + session.context_summary[:1200] if session.context_summary else "")
            + "\n\nПОСЛЕДНИЕ РЕПЛИКИ:\n"
            + json.dumps(recent_conversation_messages(session.raw_messages, max_turns=6), ensure_ascii=False)
        )
        gated_chunks = _quality_gated_chunks(
            streamer,
            tool_mode=use_tools,
            early_stream=False,
            repair_prompt=repair_prompt,
        )
        reply_parts = []
        async for chunk in gated_chunks:
            reply_parts.append(chunk)
            yield chunk
        reply = "".join(reply_parts)
        if not private_mode:
            _append(session, "assistant", reply)
            _update_conversation_state(session, text)
            if not ephemeral_request:
                await remember(db, user_id, explicit_fact or text, source="explicit_memory" if explicit_fact else "user_message", categories=list(new_facts))
            trace = tool_trace()
            append_action(user, "chat", "ok", route=conversation_mode(text), count=len(trace))
            for item in trace:
                append_action(user, "tool", item["status"], tool=item["tool"])
        await db.commit()
