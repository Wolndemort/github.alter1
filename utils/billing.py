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
    for value in ((config.OWNER_TELEGRAM_IDS or "") + "," + (config.OWNER_WEB_USER_IDS or "")).split(","):
        try:
            result.add(int(value.strip()))
        except ValueError:
            continue
    return result


def is_owner(user_id: int) -> bool:
    return user_id in owner_ids()


def owner_emails() -> set[str]:
    return {value.strip().casefold() for value in (config.OWNER_EMAILS or "").split(",") if value.strip()}


def has_owner_access(user_id: int, email: str | None = None) -> bool:
    return is_owner(user_id) or bool(email and email.strip().casefold() in owner_emails())


PLANS = {
    "personal": {"name": "ALTER Personal", "price": "990.00", "credits": config.PERSONAL_MONTHLY_CREDITS},
    "ego": {"name": "ALTER Ego", "price": "2990.00", "credits": config.EGO_MONTHLY_CREDITS},
}

# Purchased credits are account-wide, never expire and never extend a subscription.
CREDIT_PACKS = {
    "credits_500": {"name": "500 кредитов", "credits": 500, "price": "490.00"},
    "credits_1500": {"name": "1500 кредитов", "credits": 1500, "price": "990.00"},
    "credits_3500": {"name": "3500 кредитов", "credits": 3500, "price": "1990.00"},
}


def normalize_plan(value: object) -> str:
    return str(value or "personal").strip().casefold() if str(value or "personal").strip().casefold() in PLANS else "personal"


def plan_info(plan: object = "personal") -> dict:
    return PLANS[normalize_plan(plan)]


def normalize_pack(value: object) -> str:
    key = str(value or "").strip().casefold()
    return key if key in CREDIT_PACKS else "credits_500"


def pack_info(pack: object = "credits_500") -> dict:
    return CREDIT_PACKS[normalize_pack(pack)]


def credits_limit(user: User | None) -> int:
    """Return the monthly credit quota for the user's active plan."""
    if user is None:
        return int(config.PERSONAL_MONTHLY_CREDITS)
    if has_active_trial(user):
        return int(config.TRIAL_CREDITS)
    return int(plan_info((user.tech_stack or {}).get("subscription_plan"))["credits"])


def effective_plan(user_id: int, user: User | None, email: str | None = None) -> str:
    """Show owner access as the highest plan in account and usage views."""
    if has_owner_access(user_id, email):
        return "ego"
    return normalize_plan((user.tech_stack or {}).get("subscription_plan")) if user else "personal"


def price(plan: object = "personal") -> Decimal:
    try:
        configured = config.SUBSCRIPTION_PRICE_RUB if normalize_plan(plan) == "personal" else config.EGO_PRICE_RUB
        value = Decimal(configured).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError):
        raise RuntimeError("Invalid SUBSCRIPTION_PRICE_RUB")
    if value <= 0:
        raise RuntimeError("SUBSCRIPTION_PRICE_RUB must be positive")
    return value


def has_active_subscription(user: User | None) -> bool:
    if not user:
        return False
    now = datetime.now(timezone.utc)
    if user.subscription_expires_at and user.subscription_expires_at > now:
        return True
    started = (user.tech_stack or {}).get("trial_started_at")
    try:
        trial_start = datetime.fromisoformat(str(started).replace("Z", "+00:00")) if started else None
    except ValueError:
        trial_start = None
    return bool(trial_start and trial_start + timedelta(days=config.TRIAL_DAYS) > now)


def has_active_trial(user: User | None) -> bool:
    if not user or (user.subscription_expires_at and user.subscription_expires_at > datetime.now(timezone.utc)):
        return False
    started = (user.tech_stack or {}).get("trial_started_at")
    try:
        value = datetime.fromisoformat(str(started).replace("Z", "+00:00")) if started else None
    except ValueError:
        return False
    return bool(value and value + timedelta(days=config.TRIAL_DAYS) > datetime.now(timezone.utc))


def has_paid_subscription(user: User | None) -> bool:
    """Return only a real paid subscription, excluding the introductory trial."""
    return bool(user and user.subscription_expires_at and user.subscription_expires_at > datetime.now(timezone.utc))


def configured() -> bool:
    return bool(config.YUKASSA_SHOP_ID and config.YUKASSA_SECRET_KEY)


async def create_payment(session: AsyncSession, user: User, bot_username: str, payment_method_type: str = "bank_card", plan: str = "personal", return_url: str | None = None) -> str:
    if not configured():
        raise RuntimeError("YooKassa is not configured")
    key = f"alter-{user.id}-{uuid.uuid4().hex}"
    plan = normalize_plan(plan)
    amount = price(plan)
    payment = Payment(user_id=user.id, idempotence_key=key, amount_rub=str(amount), status="pending")
    session.add(payment)
    await session.flush()
    payment_method_type = payment_method_type if payment_method_type in {"bank_card", "sbp"} else "bank_card"
    payload = {
        "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": return_url or f"https://t.me/{bot_username}?start=payment_{key}",
        },
        "metadata": {"user_id": str(user.id), "payment_key": key, "plan": plan},
        "description": f"ALTER — доступ на {config.SUBSCRIPTION_DAYS} дней",
    }
    if payment_method_type == "sbp":
        payload["payment_method_data"] = {"type": "sbp"}
    elif config.YUKASSA_SAVE_PAYMENT_METHOD:
        # Saving a card enables recurring charges but some cards/stores reject
        # the initial payment entirely when this flag is present. One-time
        # payment is the safe default; recurring billing is opt-in.
        payload["save_payment_method"] = True
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


async def create_credit_payment(session: AsyncSession, user: User, bot_username: str, payment_method_type: str = "bank_card", pack: str = "credits_500", return_url: str | None = None) -> str:
    if not configured():
        raise RuntimeError("YooKassa is not configured")
    key = f"alter-credits-{user.id}-{uuid.uuid4().hex}"
    pack = normalize_pack(pack)
    details = pack_info(pack)
    amount = Decimal(details["price"])
    payment = Payment(user_id=user.id, idempotence_key=key, amount_rub=str(amount), status="pending")
    session.add(payment)
    await session.flush()
    payload = {
        "amount": {"value": f"{amount:.2f}", "currency": "RUB"}, "capture": True,
        "confirmation": {"type": "redirect", "return_url": return_url or f"https://t.me/{bot_username}?start=payment_{key}"},
        "metadata": {"user_id": str(user.id), "payment_key": key, "type": "credit_pack", "pack": pack},
        "description": f"ALTER — {details['name']} (без продления подписки)",
    }
    if payment_method_type == "sbp":
        payload["payment_method_data"] = {"type": "sbp"}
    elif config.YUKASSA_SAVE_PAYMENT_METHOD:
        payload["save_payment_method"] = True
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
    payment = (await session.execute(
        select(Payment).where(Payment.idempotence_key == payment_key).with_for_update()
    )).scalar_one_or_none()
    if not payment or not configured() or not payment.provider_payment_id:
        return False
    async with httpx.AsyncClient(auth=(config.YUKASSA_SHOP_ID, config.YUKASSA_SECRET_KEY.get_secret_value()), timeout=15) as client:
        response = await client.get(f"https://api.yookassa.ru/v3/payments/{payment.provider_payment_id}")
    data = response.json()
    actual = data.get("amount") or {}
    metadata = data.get("metadata") or {}
    if response.status_code != 200 or data.get("status") != "succeeded" or not data.get("paid"):
        return False
    if metadata.get("payment_key") != payment_key or str(metadata.get("user_id")) != str(payment.user_id):
        return False
    payment_type = metadata.get("type", "subscription")
    pack = normalize_pack(metadata.get("pack"))
    plan = normalize_plan(metadata.get("plan"))
    expected = Decimal(pack_info(pack)["price"]) if payment_type == "credit_pack" else price(plan)
    if actual.get("currency") != "RUB" or Decimal(str(actual.get("value", "0"))) != expected:
        return False
    if payment.status == "succeeded":
        return True
    user = await session.get(User, payment.user_id, with_for_update=True)
    if not user:
        return False
    now = datetime.now(timezone.utc)
    if payment_type == "credit_pack":
        user.credit_balance = int(user.credit_balance or 0) + int(pack_info(pack)["credits"])
    else:
        base = user.subscription_expires_at if has_active_subscription(user) else now
        user.subscription_expires_at = base + timedelta(days=config.SUBSCRIPTION_DAYS)
        settings = dict(user.tech_stack or {})
        settings["subscription_plan"] = plan
        user.tech_stack = settings
        payment_method = (data.get("payment_method") or {}).get("id")
        if payment_method:
            user.payment_method_id = str(payment_method)
        user.next_charge_at = user.subscription_expires_at
    payment.status = "succeeded"
    payment.paid_at = now
    await session.commit()
    return True


async def charge_recurring_payment(session: AsyncSession, user: User) -> str:
    """Charge a saved YooKassa payment method once and extend the subscription."""
    if not configured() or not user.payment_method_id or not user.auto_renew:
        return "skipped"
    plan = normalize_plan((user.tech_stack or {}).get("subscription_plan"))
    amount = price(plan)
    key = f"alter-renew-{user.id}-{(user.next_charge_at or datetime.now(timezone.utc)).date().isoformat()}"
    existing = (await session.execute(select(Payment).where(Payment.idempotence_key == key))).scalar_one_or_none()
    if existing and existing.status == "succeeded":
        return "already_paid"
    payload = {
        "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
        "capture": True,
        "payment_method_id": user.payment_method_id,
        "metadata": {"user_id": str(user.id), "payment_key": key, "type": "recurring", "plan": plan},
        "description": f"ALTER — автопродление на {config.SUBSCRIPTION_DAYS} дней",
    }
    if config.YUKASSA_RECEIPT_EMAIL:
        payload["receipt"] = {
            "customer": {"email": config.YUKASSA_RECEIPT_EMAIL},
            "items": [{
                "description": "Автопродление доступа к AI-ассистенту ALTER",
                "quantity": "1.00",
                "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
                "vat_code": 1,
                "payment_mode": "full_payment",
                "payment_subject": "service",
            }],
        }
    async with httpx.AsyncClient(auth=(config.YUKASSA_SHOP_ID, config.YUKASSA_SECRET_KEY.get_secret_value()), timeout=15) as client:
        response = await client.post(
            "https://api.yookassa.ru/v3/payments",
            json=payload,
            headers={"Idempotence-Key": key},
        )
    data = response.json()
    if response.status_code not in {200, 201} or data.get("status") not in {"succeeded", "pending", "waiting_for_capture"}:
        user.auto_renew = False
        await session.commit()
        return "failed"
    if data.get("status") != "succeeded":
        if existing is None:
            session.add(Payment(
                user_id=user.id,
                provider_payment_id=data.get("id"),
                idempotence_key=key,
                amount_rub=str(amount),
                status="pending",
            ))
        user.next_charge_at = datetime.now(timezone.utc) + timedelta(
            seconds=max(3600, config.SUBSCRIPTION_RENEWAL_CHECK_SECONDS)
        )
        await session.commit()
        return "pending"
    now = datetime.now(timezone.utc)
    base = user.subscription_expires_at if has_active_subscription(user) else now
    user.subscription_expires_at = base + timedelta(days=config.SUBSCRIPTION_DAYS)
    user.next_charge_at = user.subscription_expires_at
    user.payment_method_id = str((data.get("payment_method") or {}).get("id") or user.payment_method_id)
    if existing:
        existing.provider_payment_id = data.get("id")
        existing.status = "succeeded"
        existing.paid_at = now
    else:
        session.add(Payment(
            user_id=user.id,
            provider_payment_id=data.get("id"),
            idempotence_key=key,
            amount_rub=str(amount),
            status="succeeded",
            paid_at=now,
        ))
    await session.commit()
    return "succeeded"
