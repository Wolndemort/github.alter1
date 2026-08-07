import asyncio
import logging
import re
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
from utils.helpers import merge_memory
from utils.user_settings import DEFAULT_HEALTH_FOLLOWUP_HOURS, is_quiet_time, user_setting
from utils.billing import charge_recurring_payment, create_payment, has_active_subscription
from utils.vector_memory import purge_expired
from utils.push_notifications import send_push


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


def extract_health_followup(messages: list, now: datetime | None = None) -> dict | None:
    """Create one gentle follow-up when a user mentions a health problem."""
    for message in messages or []:
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
    facts = await summarize_session(session.raw_messages)
    if not facts or not session.user:
        return False
    current = dict(session.user.memory or {})
    session.user.memory = merge_memory(current, facts)
    flag_modified(session.user, "memory")
    for event in extract_important_events(facts):
        await save_unique_event(event, session.user.id, db)
    for followup in extract_followups(facts):
        # Idempotency: a repeated session summary must not schedule duplicates.
        existing = await db.execute(select(Reminder).where(
            Reminder.user_id == session.user.id,
            Reminder.kind == "followup",
            Reminder.text == followup["text"],
            Reminder.remind_at == followup["remind_at"],
        ))
        if existing.scalar_one_or_none() is None:
            db.add(Reminder(user_id=session.user.id, kind="followup", **followup))
    health_followup = extract_health_followup(session.raw_messages)
    if health_followup and session.user.checkins_enabled:
        hours = max(1, min(48, int(user_setting(session.user, "health_followup_hours", DEFAULT_HEALTH_FOLLOWUP_HOURS))))
        health_followup["remind_at"] = datetime.now(timezone.utc) + timedelta(hours=hours)
        # Do not create a second health check-in while one is still pending.
        if hasattr(db, "execute"):
            existing = await db.execute(select(Reminder).where(
                Reminder.user_id == session.user.id,
                Reminder.kind == "health_checkin",
                Reminder.is_sent.is_(False),
                Reminder.remind_at > datetime.now(timezone.utc),
            ))
            if existing.scalar_one_or_none() is None:
                db.add(Reminder(user_id=session.user.id, kind="health_checkin", **health_followup))
        else:
            db.add(Reminder(user_id=session.user.id, kind="health_checkin", **health_followup))
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
                sessions = result.scalars().all()

                for session in sessions:
                    try:
                        if not await process_session(session, db):
                            await db.rollback()
                    except Exception:
                        await db.rollback()
                        logging.exception("Failed to process session %s", session.id)
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
                    memory = user.memory or {}
                    if not any(memory.get(key) for key in (
                        "psycho_vibe", "health_sport", "important_events",
                        "open_loops", "goals_habits",
                    )):
                        continue
                    interval = max(1, min(168, int(user_setting(user, "checkin_interval_hours", 24))))
                    if user.last_checkin_at and user.last_checkin_at > now - timedelta(hours=interval):
                        continue
                    # Сначала возвращаемся к конкретным незавершённым темам и событиям,
                    # а не к общему настроению: так не теряются обещанные follow-up.
                    context = (memory.get("open_loops") or memory.get("health_sport") or
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
                    session_result = await db.execute(select(Session).where(
                        Session.user_id == user.id,
                    ).order_by(Session.updated_at.desc()).limit(1))
                    session = session_result.scalar_one_or_none()
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
    """Send exactly one reminder per expiry date at 5, 3 and 1 day before expiry."""
    while True:
        try:
            async with async_session() as db:
                now = datetime.now(timezone.utc)
                result = await db.execute(
                    select(User).options(selectinload(User.web_account)).where(User.subscription_expires_at > now).with_for_update(skip_locked=True)
                )
                bot_user = await bot.get_me()
                for user in result.scalars().all():
                    if not user.subscription_expires_at or not has_active_subscription(user):
                        continue
                    seconds_left = (user.subscription_expires_at - now).total_seconds()
                    days_left = int((seconds_left + 86399) // 86400)
                    if days_left not in {5, 3, 1}:
                        continue
                    expiry_key = user.subscription_expires_at.isoformat()
                    marker = f"{expiry_key}:{days_left}"
                    reminders = dict(user.subscription_reminders or {})
                    if reminders.get(marker):
                        continue
                    chat_id = telegram_chat_id(user)
                    if chat_id is None:
                        continue
                    try:
                        payment_url = await create_payment(db, user, bot_user.username or "", "bank_card")
                        await bot.send_message(
                            chat_id,
                            subscription_expiry_reminder(days_left, user.first_name, bool(user.auto_renew)),
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                [InlineKeyboardButton(text="💳 Продлить подписку", url=payment_url)],
                            ]),
                        )
                    except Exception:
                        await db.rollback()
                        logging.exception("Subscription expiry reminder failed for user %s", user.id)
                        continue
                    reminders[marker] = now.isoformat()
                    user.subscription_reminders = dict(list(reminders.items())[-30:])
                    await db.commit()
        except Exception:
            logging.exception("Subscription expiry reminder monitor failed")
        await asyncio.sleep(3600)
