"""YooKassa payments and one-month subscription activation."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import config
from data.models import Payment, User


def owner_ids() -> set[int]:
    result = set()
    for value in (config.OWNER_TELEGRAM_IDS or "").split(","):
        try:
            result.add(int(value.strip()))
        except ValueError:
            continue
    return result


def is_owner(user_id: int) -> bool:
    return user_id in owner_ids()


def price() -> Decimal:
    try:
        value = Decimal(config.SUBSCRIPTION_PRICE_RUB).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError):
        raise RuntimeError("Invalid SUBSCRIPTION_PRICE_RUB")
    if value <= 0:
        raise RuntimeError("SUBSCRIPTION_PRICE_RUB must be positive")
    return value


def has_active_subscription(user: User | None) -> bool:
    return bool(user and user.subscription_expires_at and user.subscription_expires_at > datetime.now(timezone.utc))


def configured() -> bool:
    return bool(config.YUKASSA_SHOP_ID and config.YUKASSA_SECRET_KEY)


async def create_payment(session: AsyncSession, user: User, bot_username: str) -> str:
    if not configured():
        raise RuntimeError("YooKassa is not configured")
    key = f"alter-{user.id}-{uuid.uuid4().hex}"
    amount = price()
    payment = Payment(user_id=user.id, idempotence_key=key, amount_rub=str(amount), status="pending")
    session.add(payment)
    await session.flush()
    payload = {
        "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": f"https://t.me/{bot_username}?start=payment_{key}",
        },
        "metadata": {"user_id": str(user.id), "payment_key": key},
        "description": f"ALTER — доступ на {config.SUBSCRIPTION_DAYS} дней",
    }
    if config.YUKASSA_RECEIPT_EMAIL:
        payload["receipt"] = {
            "customer": {"email": config.YUKASSA_RECEIPT_EMAIL},
            "items": [{
                "description": "Доступ к AI-ассистенту ALTER",
                "quantity": "1.00",
                "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
                "vat_code": 1,
                "payment_mode": "full_payment",
                "payment_subject": "service",
            }],
        }
    async with httpx.AsyncClient(auth=(config.YUKASSA_SHOP_ID, config.YUKASSA_SECRET_KEY.get_secret_value()), timeout=15) as client:
        response = await client.post("https://api.yookassa.ru/v3/payments", json=payload, headers={"Idempotence-Key": key})
    data = response.json()
    if response.status_code not in {200, 201} or not data.get("id"):
        await session.delete(payment)
        await session.commit()
        raise RuntimeError(data.get("description") or "YooKassa payment creation failed")
    payment.provider_payment_id = data["id"]
    await session.commit()
    return data["confirmation"]["confirmation_url"]


async def check_and_activate(session: AsyncSession, payment_key: str) -> bool:
    payment = (await session.execute(select(Payment).where(Payment.idempotence_key == payment_key))).scalar_one_or_none()
    if not payment or not configured() or not payment.provider_payment_id:
        return False
    async with httpx.AsyncClient(auth=(config.YUKASSA_SHOP_ID, config.YUKASSA_SECRET_KEY.get_secret_value()), timeout=15) as client:
        response = await client.get(f"https://api.yookassa.ru/v3/payments/{payment.provider_payment_id}")
    data = response.json()
    expected = price()
    actual = data.get("amount") or {}
    metadata = data.get("metadata") or {}
    if response.status_code != 200 or data.get("status") != "succeeded" or not data.get("paid"):
        return False
    if metadata.get("payment_key") != payment_key or str(metadata.get("user_id")) != str(payment.user_id):
        return False
    if actual.get("currency") != "RUB" or Decimal(str(actual.get("value", "0"))) != expected:
        return False
    if payment.status == "succeeded":
        return True
    user = await session.get(User, payment.user_id, with_for_update=True)
    if not user:
        return False
    now = datetime.now(timezone.utc)
    base = user.subscription_expires_at if has_active_subscription(user) else now
    user.subscription_expires_at = base + timedelta(days=config.SUBSCRIPTION_DAYS)
    payment.status = "succeeded"
    payment.paid_at = now
    await session.commit()
    return True
