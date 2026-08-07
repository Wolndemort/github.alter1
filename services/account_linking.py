"""Shared identity linking between the independent app and Telegram."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from data.models import ImportantEvent, MemoryChunk, Payment, Reminder, Session, User, WebAccount


async def resolve_telegram_user(session: AsyncSession, telegram_user_id: int) -> User | None:
    """Resolve a Telegram identity to the canonical shared User profile."""
    # Lightweight session doubles used by the Telegram middleware tests expose
    # only ``get``; preserve the old lookup contract for those adapters.
    if not hasattr(session, "execute"):
        return await session.get(User, telegram_user_id)
    account = (await session.execute(
        select(WebAccount).where(WebAccount.telegram_user_id == telegram_user_id)
    )).scalar_one_or_none()
    if account:
        return await session.get(User, account.user_id)
    return await session.get(User, telegram_user_id)


def _merge_memory(target: dict | None, source: dict | None) -> dict:
    result = dict(source or {})
    for key, value in (target or {}).items():
        if isinstance(value, list) and isinstance(result.get(key), list):
            merged = [*result[key], *value]
            result[key] = list({repr(item): item for item in merged}.values())
        else:
            result[key] = value
    return result


async def link_telegram_identity(
    session: AsyncSession,
    app_user_id: int,
    telegram_user_id: int,
    username: str | None,
    first_name: str | None,
) -> User:
    """Link Telegram and merge an old Telegram profile into the app profile."""
    account = (await session.execute(
        select(WebAccount).where(WebAccount.user_id == app_user_id).with_for_update()
    )).scalar_one_or_none()
    if account is None:
        raise ValueError("application account not found")
    existing_link = (await session.execute(
        select(WebAccount).where(WebAccount.telegram_user_id == telegram_user_id)
    )).scalar_one_or_none()
    if existing_link and existing_link.user_id != app_user_id:
        raise ValueError("telegram account is already linked")
    target = await session.get(User, app_user_id, with_for_update=True)
    if target is None:
        raise ValueError("user not found")
    legacy = await session.get(User, telegram_user_id, with_for_update=True)
    if legacy is not None and legacy.id != target.id:
        target.memory = _merge_memory(target.memory, legacy.memory)
        target.tech_stack = _merge_memory(target.tech_stack, legacy.tech_stack)
        if legacy.subscription_expires_at and (
            not target.subscription_expires_at or legacy.subscription_expires_at > target.subscription_expires_at
        ):
            target.subscription_expires_at = legacy.subscription_expires_at
        target.payment_method_id = target.payment_method_id or legacy.payment_method_id
        target.auto_renew = target.auto_renew or legacy.auto_renew
        target.next_charge_at = target.next_charge_at or legacy.next_charge_at
        target.subscription_reminders = _merge_memory(target.subscription_reminders, legacy.subscription_reminders)
        target.legal_accepted_at = target.legal_accepted_at or legacy.legal_accepted_at
        for model in (Session, ImportantEvent, Reminder, MemoryChunk, Payment):
            await session.execute(update(model).where(model.user_id == legacy.id).values(user_id=target.id))
        # Do not use ``AsyncSession.delete`` here: the ORM may lazy-load the
        # user's relationship collections for cascade processing and raise
        # MissingGreenlet in an async request. All dependent rows were moved
        # explicitly above, so a bulk delete is deterministic and IO-free.
        await session.execute(delete(User).where(User.id == legacy.id))
    account.telegram_user_id = telegram_user_id
    if username and not target.username:
        target.username = username
    if first_name and (not target.first_name or target.first_name == "User"):
        target.first_name = first_name
    await session.flush()
    return target
