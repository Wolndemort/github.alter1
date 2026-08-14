import asyncio
import logging
import re
from math import ceil
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified
from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import config
from data.database import async_session
from data.models import ImportantEvent, Reminder, Session
from data.models import User
from utils.checkins import generate_contextual_checkin
from utils.ap_logic import summarize_session
from utils.memory_store import merge_memory_facts
from utils.user_settings import DEFAULT_HEALTH_FOLLOWUP_HOURS, is_quiet_time, user_setting
from utils.billing import charge_recurring_payment, credits_limit, has_active_subscription, has_active_trial, has_owner_access
from utils.vector_memory import purge_expired
from utils.memory_store import purge_expired_memory
from utils.memory_quality import sanitize_summary
from utils.push_notifications import send_push
from utils.weather import get_weather
from services.agent_executor import model_agent_executor, run_agent_steps
from utils.metrics_persistence import persist_metrics_snapshot
from utils.personal_notifications import deliver_reminder, quota_reminder_text, subscription_reminder_text
from utils.redis_store import close_redis, create_redis, credits_used


def telegram_chat_id(user: User) -> int | None:
    """Return the Telegram destination, or None for an app-only account.

    Legacy Telegram profiles use their User.id as the chat id. App accounts
    must use the explicitly linked id; their internal database id is not a
    Telegram chat and sending to it produces ``chat not found``.
    """
    account = user.web_account
    if account is not None:
        return account.telegram_user_id
    return user.id


async def monitor_metrics():
    """Keep aggregate diagnostics history alive across process restarts."""
    while True:
        try:
            await persist_metrics_snapshot()
        except Exception:
            logging.exception("Metrics snapshot persistence failed")
        await asyncio.sleep(60)


def active_open_loops(memory: dict | None) -> list:
    raw = (memory or {}).get("open_loops") or []
    if isinstance(raw, dict):
        raw = [raw]
    return [item for item in raw if not isinstance(item, dict) or item.get("status", "active") in {"active", "snoozed"}]


def proactive_allowed(user: User, now: datetime, session: Session | None, interval_hours: int) -> bool:
    if (user.tech_stack or {}).get("proactive_enabled", True) is False:
        return False
    if user.last_checkin_at and user.last_checkin_at > now - timedelta(hours=interval_hours):
        return False
    return not (session and session.updated_at and session.updated_at > now - timedelta(minutes=30))


def trial_onboarding_stage(user: User, now: datetime) -> tuple[int, str] | None:
    """Return one idempotent onboarding stage for a new trial user."""
    if not has_active_trial(user) or not (user.tech_stack or {}).get("proactive_enabled", True):
        return None
    started = (user.tech_stack or {}).get("trial_started_at")
    try:
        began = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if began.tzinfo is None:
        began = began.replace(tzinfo=timezone.utc)
    day = max(0, min(2, int((now - began).total_seconds() // 86400)))
    messages = (
        f"Привет, {user.first_name or 'друг'}! Я ALTER. Давай быстро настроим меня под тебя: расскажи, чем ты сейчас занимаешься и какую одну задачу хочешь закрыть первой.",
        "Я помню контекст нашего знакомства. Могу помочь с планом, поиском, файлами, голосом и напоминаниями. Что сейчас было бы для тебя самым полезным?",
        "Твой пробный доступ скоро закончится. За эти дни ALTER может сохранить твои предпочтения, планы и рабочий контекст — после trial это продолжится по подписке без потери памяти.",
    )
    sent = (user.tech_stack or {}).get("trial_onboarding_sent") or {}
    if str(day) in sent:
        return None
    return day, messages[day]


def extract_health_followup(messages: list, now: datetime | None = None) -> dict | None:
    """Create one gentle follow-up when a user mentions a health problem."""
    for message in messages or []:
        if not isinstance(message, dict):
            continue
        if message.get("role") != "user":
            continue
        text = str(message.get("content") or "").strip()
        lowered = text.casefold()
        if re.search(r"\b(?:не\s+болит|ничего\s+не\s+болит|не\s+больно)\b", lowered):
            continue
        if re.search(r"\b(?:болит|боль|температур|тошнит|плохо\s+себя|самочувств|головн|спин[аеу])", lowered):
            current = now or datetime.now(timezone.utc)
            return {"text": "Как ты себя чувствуешь? Стало лучше?", "remind_at": current + timedelta(hours=4)}
    return None


def extract_important_events(facts: dict) -> list[dict]:
    raw = facts.get("important_events", [])
    if isinstance(raw, dict): raw = [raw]
    if not isinstance(raw, list): return []
    result = []
    for item in raw:
        if not isinstance(item, dict): continue
        title = str(item.get("title") or item.get("event") or "").strip()
        if not title: continue
        try:
            confidence = max(0.0, min(1.0, float(item.get("confidence", 0.8))))
        except (TypeError, ValueError):
            confidence = 0.8
        result.append({
            "event_type": str(item.get("event_type") or "general")[:32],
            "title": title[:200],
            "description": item.get("description"),
            "importance": str(item.get("importance") or "normal")[:16],
            "source": "session_summary",
            "confidence": confidence,
            "details": item,
        })
    return result


def extract_followups(facts: dict) -> list[dict]:
    """Turn model-detected future topics into concrete reminder payloads."""
    raw = facts.get("open_loops", [])
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    result = []
    for item in raw:
        if not isinstance(item, dict) or not item.get("follow_up_at"):
            continue
        title = str(item.get("follow_up_question") or item.get("title") or "").strip()
        if not title:
            continue
        try:
            remind_at = datetime.fromisoformat(str(item["follow_up_at"]).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
        if remind_at.tzinfo is None:
            remind_at = remind_at.replace(tzinfo=timezone.utc)
        result.append({"text": title[:500], "remind_at": remind_at})
    return result


async def save_unique_event(event: dict, user_id: int, db) -> None:
    """Persist an event only once per user and title."""
    if not hasattr(db, "execute"):
        db.add(ImportantEvent(user_id=user_id, **event))
        return
    existing = await db.execute(select(ImportantEvent).where(
        ImportantEvent.user_id == user_id,
        ImportantEvent.title == event["title"],
    ))
    if existing.scalar_one_or_none() is None:
        db.add(ImportantEvent(user_id=user_id, **event))


async def process_session(session: Session, db) -> bool:
    """Summarize one inactive session and persist its durable memory."""
    messages = [item for item in (session.raw_messages or []) if isinstance(item, dict)]
    facts = sanitize_summary(await summarize_session(messages))
    if not facts:
        # A failed/empty summary must not leave the session active forever.
        # The next "new chat" should always start from a clean context.
        session.is_processed = True
        await db.commit()
        return False
    # Resolve the owner explicitly. Accessing ``session.user`` can trigger a
    # lazy async query after a rollback and raise MissingGreenlet.
    user = await db.get(User, session.user_id) if hasattr(db, "get") else session.user
    if user is None:
        return False
    current = dict(user.memory) if isinstance(user.memory, dict) else {}
    user.memory = merge_memory_facts(current, facts)
    flag_modified(user, "memory")
    for event in extract_important_events(facts):
        await save_unique_event(event, user.id, db)
    for followup in extract_followups(facts):
        # Idempotency: a repeated session summary must not schedule duplicates.
        existing = await db.execute(select(Reminder).where(
            Reminder.user_id == user.id,
            Reminder.kind == "followup",
            Reminder.text == followup["text"],
            Reminder.remind_at == followup["remind_at"],
        ))
        if existing.scalar_one_or_none() is None:
            db.add(Reminder(user_id=user.id, kind="followup", **followup))
    health_followup = extract_health_followup(messages)
    if health_followup and user.checkins_enabled:
        hours = max(1, min(48, int(user_setting(user, "health_followup_hours", DEFAULT_HEALTH_FOLLOWUP_HOURS))))
        health_followup["remind_at"] = datetime.now(timezone.utc) + timedelta(hours=hours)
        # Do not create a second health check-in while one is still pending.
        if hasattr(db, "execute"):
            existing = await db.execute(select(Reminder).where(
                Reminder.user_id == user.id,
                Reminder.kind == "health_checkin",
                Reminder.is_sent.is_(False),
                Reminder.remind_at > datetime.now(timezone.utc),
            ))
            if existing.scalar_one_or_none() is None:
                db.add(Reminder(user_id=user.id, kind="health_checkin", **health_followup))
        else:
            db.add(Reminder(user_id=user.id, kind="health_checkin", **health_followup))
    session.is_processed = True
    await db.commit()
    return True


async def monitor_personality_imprint():
    """Periodically turns inactive chat sessions into long-term memory."""
    while True:
        try:
            async with async_session() as db:
                threshold = datetime.now(timezone.utc) - timedelta(seconds=config.SESSION_TIMEOUT)
                result = await db.execute(
                    select(Session)
                    .where(Session.is_processed.is_(False), Session.updated_at < threshold)
                    .with_for_update(skip_locked=True)
                    .options(selectinload(Session.user))
                )
                session_ids = [session.id for session in result.scalars().all()]

                # Rollback expires ORM instances. Never reuse the original
                # list after a rollback: re-fetch each row explicitly so a
                # column access cannot trigger hidden async IO (MissingGreenlet).
                for session_id in session_ids:
                    session = await db.get(Session, session_id)
                    if session is None:
                        continue
                    try:
                        if not await process_session(session, db):
                            await db.rollback()
                    except Exception:
                        await db.rollback()
                        logging.exception("Failed to process session %s", session_id)
        except Exception:
            logging.exception("Background memory monitor failed")

        await asyncio.sleep(30)


async def monitor_memory_cleanup():
    """Remove expired episodic memories once a day in bounded batches."""
    while True:
        try:
            async with async_session() as db:
                removed = await purge_expired(db)
                if removed:
                    logging.info("Expired vector memories removed: %s", removed)
                users = (await db.execute(select(User).order_by(User.id).limit(500))).scalars().all()
                structured_removed = 0
                for user in users:
                    cleaned = purge_expired_memory(user.memory or {})
                    if cleaned != (user.memory or {}):
                        user.memory = cleaned
                        flag_modified(user, "memory")
                        structured_removed += 1
                if structured_removed:
                    await db.commit()
                    logging.info("Expired structured memories removed: %s", structured_removed)
        except Exception:
            logging.exception("Vector memory cleanup failed")
        await asyncio.sleep(86400)


async def monitor_reminders(bot: Bot):
    """Send due one-time reminders."""
    while True:
        try:
            async with async_session() as db:
                now = datetime.now(timezone.utc)
                result = await db.execute(select(Reminder).where(
                    ((Reminder.is_sent.is_(False)) & (Reminder.remind_at <= now)) |
                    ((Reminder.is_sent.is_(True)) & (Reminder.follow_up_sent.is_(False)) & (Reminder.follow_up_at <= now))
                ).with_for_update(skip_locked=True))
                for reminder in result.scalars().all():
                    try:
                        user = (await db.execute(
                            select(User).options(selectinload(User.web_account)).where(
                                User.id == reminder.user_id
                            )
                        )).scalar_one_or_none()
                        if user and is_quiet_time(user, now):
                            continue
                        if not reminder.is_sent:
                            if reminder.kind in {"checkin", "health_checkin"}:
                                session_result = await db.execute(select(Session).where(
                                    Session.user_id == reminder.user_id,
                                ).order_by(Session.updated_at.desc()).limit(1))
                                session = session_result.scalar_one_or_none()
                                question = await generate_contextual_checkin(
                                    user.first_name,
                                    reminder.text,
                                    session.raw_messages if session else [],
                                    user.memory or {},
                                )
                                chat_id = telegram_chat_id(user)
                                if chat_id is not None:
                                    await bot.send_message(chat_id, question)
                                await send_push(user, "ALTER", question)
                            else:
                                notification = f"Напоминание: {reminder.text}"
                                chat_id = telegram_chat_id(user)
                                if chat_id is not None:
                                    await bot.send_message(chat_id, f"⏰ {notification}")
                                await send_push(user, "ALTER · Напоминание", notification)
                            reminder.is_sent = True
                        elif reminder.follow_up_at and not reminder.follow_up_sent and reminder.follow_up_at <= datetime.now(timezone.utc):
                            session_result = await db.execute(select(Session).where(
                                Session.user_id == reminder.user_id,
                            ).order_by(Session.updated_at.desc()).limit(1))
                            session = session_result.scalar_one_or_none()
                            question = await generate_contextual_checkin(
                                user.first_name,
                                reminder.text,
                                session.raw_messages if session else [],
                                user.memory or {},
                            )
                            chat_id = telegram_chat_id(user)
                            if chat_id is not None:
                                await bot.send_message(chat_id, question)
                            await send_push(user, "ALTER · Check-in", question)
                            reminder.follow_up_sent = True
                    except Exception:
                        logging.exception("Failed to send reminder %s", reminder.id)
                await db.commit()
        except Exception:
            logging.exception("Reminder monitor failed")
        await asyncio.sleep(30)


async def monitor_checkins(bot: Bot):
    """Send one contextual pulse only when it can genuinely help."""
    while True:
        try:
            async with async_session() as db:
                now = datetime.now(timezone.utc)
                result = await db.execute(
                    select(User).options(selectinload(User.web_account)).where(
                        User.checkins_enabled.is_(True)
                    ).with_for_update(skip_locked=True)
                )
                for user in result.scalars().all():
                    onboarding = trial_onboarding_stage(user, now)
                    if onboarding and not is_quiet_time(user, now):
                        session_result = await db.execute(select(Session).where(
                            Session.user_id == user.id,
                        ).order_by(Session.updated_at.desc()).limit(1))
                        session = session_result.scalar_one_or_none()
                        if proactive_allowed(user, now, session, 20):
                            _, message = onboarding
                            chat_id = telegram_chat_id(user)
                            if chat_id is not None:
                                await bot.send_message(chat_id, message)
                            await send_push(user, "ALTER · Пробный доступ", message)
                            settings = dict(user.tech_stack or {})
                            sent = dict(settings.get("trial_onboarding_sent") or {})
                            sent[str(onboarding[0])] = now.isoformat()
                            settings["trial_onboarding_sent"] = sent
                            user.tech_stack = settings
                            user.last_checkin_at = now
                            continue
                    memory = user.memory or {}
                    if not any(memory.get(key) for key in (
                        "psycho_vibe", "health_sport", "important_events",
                        "open_loops", "goals_habits",
                    )):
                        continue
                    interval = max(1, min(168, int(user_setting(user, "checkin_interval_hours", 24))))
                    if user.last_checkin_at and user.last_checkin_at > now - timedelta(hours=interval):
                        continue
                    session_result = await db.execute(select(Session).where(
                        Session.user_id == user.id,
                    ).order_by(Session.updated_at.desc()).limit(1))
                    session = session_result.scalar_one_or_none()
                    # Do not interrupt a fresh conversation. The active chat
                    # itself is more important than a background nudge.
                    if not proactive_allowed(user, now, session, interval):
                        continue
                    # Сначала возвращаемся к конкретным незавершённым темам и событиям,
                    # а не к общему настроению: так не теряются обещанные follow-up.
                    active_loops = active_open_loops(memory)
                    context = (active_loops or memory.get("health_sport") or
                               memory.get("important_events") or memory.get("goals_habits") or
                               memory.get("skills_career"))
                    if isinstance(context, dict):
                        context = next((str(value) for value in context.values() if value), None)
                    if isinstance(context, list) and context:
                        item = context[-1]
                        context = item.get("title") if isinstance(item, dict) else str(item)
                    if not context and memory.get("important_events"):
                        events = memory["important_events"]
                        event = events[-1] if isinstance(events, list) else events
                        context = event.get("title") if isinstance(event, dict) else str(event)
                    question = await generate_contextual_checkin(
                        user.first_name,
                        context,
                        session.raw_messages if session else [],
                        memory,
                    )
                    chat_id = telegram_chat_id(user)
                    if chat_id is not None:
                        await bot.send_message(chat_id, question)
                    await send_push(user, "ALTER · Check-in", question)
                    user.last_checkin_at = now
                await db.commit()
        except Exception:
            logging.exception("Gentle check-in monitor failed")
        await asyncio.sleep(300)


async def monitor_daily_briefs(bot: Bot):
    """Send one concise morning and evening brief per user in Moscow time."""
    while True:
        try:
            async with async_session() as db:
                now = datetime.now(timezone.utc)
                local_now = now + timedelta(hours=3)
                marker_day = local_now.date().isoformat()
                result = await db.execute(select(User).options(selectinload(User.web_account)).where(User.checkins_enabled.is_(True)))
                for user in result.scalars().all():
                    settings = dict(user.tech_stack or {})
                    if settings.get("proactive_enabled", True) is False or is_quiet_time(user, now):
                        continue
                    memory = user.memory or {}
                    loops = active_open_loops(memory)
                    location = settings.get("current_location") if isinstance(settings.get("current_location"), dict) else {}
                    city = str(location.get("city") or location.get("region") or "Москва").strip()
                    marker = f"{marker_day}:{local_now.hour}"
                    sent = dict(settings.get("daily_briefs_sent") or {})
                    if local_now.hour == 9 and sent.get(f"morning:{marker_day}") is None:
                        weather = await get_weather(city) or f"Погоду для {city} пока не удалось получить."
                        focus = str(loops[0].get("title") if loops and isinstance(loops[0], dict) else (memory.get("goals_habits") or {}).get("goal") or "Выбери одну главную задачу на сегодня.")
                        message = f"Доброе утро, {user.first_name or 'друг'}!\n\n{weather}\n\nГлавный фокус: {focus[:240]}"
                        chat_id = telegram_chat_id(user)
                        if chat_id is not None: await bot.send_message(chat_id, message)
                        await send_push(user, "ALTER · Доброе утро", message)
                        sent[f"morning:{marker_day}"] = now.isoformat()
                    elif local_now.hour == 21 and sent.get(f"evening:{marker_day}") is None:
                        focus = str(loops[0].get("title") if loops and isinstance(loops[0], dict) else "Незавершённых тем пока нет.")
                        message = f"Вечерний чек-ин ALTER.\n\nЧто получилось сегодня? Если хочешь, завтра вернёмся к теме: {focus[:240]}"
                        chat_id = telegram_chat_id(user)
                        if chat_id is not None: await bot.send_message(chat_id, message)
                        await send_push(user, "ALTER · Вечерний итог", message)
                        sent[f"evening:{marker_day}"] = now.isoformat()
                    else:
                        continue
                    settings["daily_briefs_sent"] = dict(list(sent.items())[-14:])
                    user.tech_stack = settings
                await db.commit()
        except Exception:
            logging.exception("Daily brief monitor failed")
        await asyncio.sleep(60)


def _agent_due(state: dict, now: datetime) -> bool:
    if not state.get("autonomy_enabled") or state.get("status") != "active":
        return False
    try:
        due = datetime.fromisoformat(str(state.get("next_run_at") or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return True
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    return due <= now


async def process_autonomous_agent(user: User, bot: Bot | None = None, *, db=None, now: datetime | None = None) -> bool:
    """Run at most one opted-in agent step and schedule the next tick."""
    current = dict(user.tech_stack or {})
    state = dict(current.get("active_agent") or {})
    moment = now or datetime.now(timezone.utc)
    if not _agent_due(state, moment):
        return False
    if db is None:
        current = await run_agent_steps(current, model_agent_executor, max_steps=1)
    else:
        async def executor(task, state):
            return await model_agent_executor(task, state, db=db, user=user)
        current = await run_agent_steps(current, executor, max_steps=1)
    state = dict(current.get("active_agent") or {})
    if state.get("status") == "active":
        interval = max(5, min(int(state.get("check_interval_minutes", 60)), 7 * 24 * 60))
        state["next_run_at"] = (moment + timedelta(minutes=interval)).isoformat()
        current["active_agent"] = state
    user.tech_stack = current
    flag_modified(user, "tech_stack")
    status = state.get("status")
    if bot is not None and status in {"blocked", "completed"} and not is_quiet_time(user, moment):
        if status == "completed":
            message = f"Агент завершил план: {state.get('goal', '')[:180]}"
        else:
            message = f"Агент остановился на блокере: {state.get('goal', '')[:180]}. Открой план, чтобы перепланировать."
        chat_id = telegram_chat_id(user)
        if chat_id is not None:
            await bot.send_message(chat_id, message)
        await send_push(user, "ALTER · Агент", message)
    return True


async def monitor_agents(bot: Bot):
    """Tick opted-in agents without touching ordinary users or conversations."""
    while True:
        try:
            async with async_session() as db:
                now = datetime.now(timezone.utc)
                result = await db.execute(select(User).options(selectinload(User.web_account)).with_for_update(skip_locked=True))
                for user in result.scalars().all():
                    try:
                        await process_autonomous_agent(user, bot, db=db, now=now)
                    except Exception:
                        logging.exception("Autonomous agent tick failed user=%s", user.id)
                await db.commit()
        except Exception:
            logging.exception("Agent monitor failed")
        await asyncio.sleep(60)


async def monitor_subscription_renewals(bot: Bot):
    """Hourly opt-in YooKassa renewals; failed renewals disable auto-charge."""
    while True:
        try:
            async with async_session() as db:
                now = datetime.now(timezone.utc)
                result = await db.execute(select(User).options(selectinload(User.web_account)).where(
                    User.auto_renew.is_(True),
                    User.payment_method_id.is_not(None),
                    User.next_charge_at <= now,
                ).with_for_update(skip_locked=True))
                for user in result.scalars().all():
                    try:
                        result_code = await charge_recurring_payment(db, user)
                        chat_id = telegram_chat_id(user)
                        if chat_id is not None and result_code == "succeeded":
                            await bot.send_message(chat_id, "Подписка ALTER продлена ещё на 30 дней.")
                        elif chat_id is not None and result_code == "failed":
                            await bot.send_message(chat_id, "Не удалось продлить подписку. Автопродление отключено — проверь карту и продли подписку вручную через кабинет.")
                    except Exception:
                        await db.rollback()
                        logging.exception("Subscription renewal failed for user %s", user.id)
                await db.commit()
        except Exception:
            logging.exception("Subscription renewal monitor failed")
        await asyncio.sleep(max(300, config.SUBSCRIPTION_RENEWAL_CHECK_SECONDS))


def subscription_expiry_reminder(days_left: int, first_name: str, auto_renew: bool) -> str:
    """Build a warm, explicit subscription reminder without sounding alarmist."""
    name = first_name or "друг"
    if days_left == 1:
        timing = "завтра"
    elif days_left in {2, 3, 4}:
        timing = f"через {days_left} дня"
    else:
        timing = f"через {days_left} дней"
    auto_note = (
        "Автопродление уже включено — ALTER сам постарается продлить доступ."
        if auto_renew else
        "Можно включить автопродление в кабинете, чтобы не следить за датой вручную."
    )
    return (
        f"👋 {name}, напоминаю мягко: подписка ALTER закончится {timing}.\n\n"
        f"{auto_note}\n"
        "Если ничего не менять, ALTER не забудет тебя — просто напомнит продлить доступ."
    )


async def monitor_subscription_expiry_reminders(bot: Bot):
    """Send one personal reminder per expiry date at 5, 3 and 1 day before expiry."""
    while True:
        try:
            async with async_session() as db:
                now = datetime.now(timezone.utc)
                result = await db.execute(
                    select(User).options(selectinload(User.web_account)).where(User.subscription_expires_at > now).with_for_update(skip_locked=True)
                )
                for user in result.scalars().all():
                    if not user.subscription_expires_at or not has_active_subscription(user):
                        continue
                    seconds_left = (user.subscription_expires_at - now).total_seconds()
                    days_left = int((seconds_left + 86399) // 86400)
                    if days_left not in {5, 3, 1}:
                        continue
                    expiry_key = user.subscription_expires_at.isoformat()
                    try:
                        await deliver_reminder(
                            db, user, bot, subscription_reminder_text(user, days_left),
                            "ALTER · Доступ", f"subscription:{expiry_key}:{days_left}",
                        )
                    except Exception:
                        await db.rollback()
                        logging.exception("Subscription expiry reminder failed for user %s", user.id)
        except Exception:
            logging.exception("Subscription expiry reminder monitor failed")
        await asyncio.sleep(3600)


async def monitor_quota_reminders(bot: Bot):
    """Send one personal reminder as the shared monthly AI quota runs low."""
    while True:
        redis = create_redis()
        try:
            async with async_session() as db:
                now = datetime.now(timezone.utc)
                result = await db.execute(select(User).options(selectinload(User.web_account)))
                for user in result.scalars().all():
                    account = getattr(user, "web_account", None)
                    if has_owner_access(user.id, account.email if account else None):
                        continue
                    if not (has_active_subscription(user) or has_active_trial(user)):
                        continue
                    limit = credits_limit(user)
                    used = await credits_used(redis, user.id)
                    remaining = max(0, limit - used)
                    if remaining <= 0:
                        level = "depleted"
                    elif remaining <= max(3, ceil(limit * 0.1)):
                        level = "low"
                    else:
                        continue
                    try:
                        await deliver_reminder(
                            db, user, bot, quota_reminder_text(user, remaining, limit, level),
                            "ALTER · Квота", f"quota:{now:%Y-%m}:{level}",
                        )
                    except Exception:
                        await db.rollback()
                        logging.exception("Quota reminder failed for user %s", user.id)
        except Exception:
            logging.exception("Quota reminder monitor failed")
        finally:
            await close_redis(redis)
        await asyncio.sleep(3600)
