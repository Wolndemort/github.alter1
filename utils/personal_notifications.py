"""Personalized cross-client reminders for shared account events."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy import select

from data.models import Session, User
from utils.push_notifications import send_push


def _variant(seed: str, variants: tuple[str, ...]) -> str:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return variants[int.from_bytes(digest[:4], "big") % len(variants)]


def subscription_reminder_text(user: User, days_left: int) -> str:
    name = user.first_name or "друг"
    timing = "завтра" if days_left == 1 else f"через {days_left} дней"
    opening = _variant(f"subscription:{user.id}:{days_left}:opening", (
        f"{name}, неудобно напоминать, но хочу предупредить заранее.",
        f"{name}, маленький heads-up от меня.",
        f"{name}, поймал важный момент по твоему доступу.",
    ))
    closing = (
        "Автопродление включено — я сам постараюсь всё продлить."
        if user.auto_renew else
        "Если захочешь продолжить, продлить можно в личном кабинете ALTER."
    )
    return f"{opening} Твоя подписка ALTER заканчивается {timing}.\n\n{closing}"


def quota_reminder_text(user: User, remaining: int, limit: int, level: str) -> str:
    name = user.first_name or "друг"
    opening = _variant(f"quota:{user.id}:{level}:{datetime.now(timezone.utc):%Y-%m}", (
        f"{name}, аккуратно напомню: у тебя осталось {remaining} AI-кредитов из {limit}.",
        f"{name}, вижу, квота уже подходит к концу — осталось {remaining} из {limit} AI-кредитов.",
        f"{name}, чтобы важная задача не оборвалась неожиданно: осталось {remaining} AI-кредитов из {limit}.",
    ))
    if level == "depleted":
        return f"{opening}\n\nМожно продолжить после обновления доступа или докупить пакет на alterai.ru."
    return f"{opening}\n\nЕсли понадобится, пополнить баланс можно на alterai.ru — остаток пакетов суммируется и не сгорает."


async def append_chat_message(db, user: User, text: str) -> None:
    """Put one assistant reminder in the shared active chat."""
    result = await db.execute(
        select(Session).where(Session.user_id == user.id, Session.is_processed.is_(False))
        .order_by(Session.started_at.desc()).limit(1)
    )
    chat = result.scalar_one_or_none()
    if chat is None:
        chat = Session(user_id=user.id, raw_messages=[])
        db.add(chat)
        await db.flush()
    messages = list(chat.raw_messages or [])
    messages.append({"role": "assistant", "content": text, "created_at": datetime.now(timezone.utc).isoformat(), "proactive": True})
    chat.raw_messages = messages[-100:]


async def deliver_reminder(db, user: User, bot, text: str, title: str, marker: str) -> bool:
    """Deliver to shared chat, inbox/push and Telegram exactly once per marker."""
    reminders = dict(user.subscription_reminders or {})
    if reminders.get(marker):
        return False
    await append_chat_message(db, user, text)
    await db.commit()
    push_text = text.split("\n\n", 1)[0] + " Открой ALTER, когда будет удобно."
    await send_push(user, title, push_text)
    reminders[marker] = datetime.now(timezone.utc).isoformat()
    user.subscription_reminders = dict(list(reminders.items())[-60:])
    await db.commit()
    account = getattr(user, "web_account", None)
    chat_id = account.telegram_user_id if account is not None else user.id
    if chat_id is not None:
        try:
            await bot.send_message(chat_id, text + "\n\nПродолжить можно на alterai.ru.")
        except Exception:
            # The durable chat, inbox and push are already delivered.
            return True
    return True
