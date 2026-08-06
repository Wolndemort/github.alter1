"""YooKassa HTTP notification handling."""
import logging

from aiohttp import web
from sqlalchemy import select

from data.database import async_session
from data.models import Payment, User
from utils.billing import check_and_activate


async def handle_yookassa_webhook(request: web.Request) -> web.Response:
    """Acknowledge provider notifications and make activation idempotent."""
    try:
        payload = await request.json()
    except (ValueError, UnicodeDecodeError):
        return web.json_response({"ok": False, "error": "invalid_json"}, status=400)

    event = payload.get("event")
    provider_object = payload.get("object") or {}
    provider_id = provider_object.get("id")
    if not provider_id:
        return web.json_response({"ok": True, "ignored": "missing_payment_id"})
    if event not in {"payment.succeeded", "payment.canceled"}:
        return web.json_response({"ok": True, "ignored": event or "unknown_event"})

    async with async_session() as session:
        payment = (await session.execute(
            select(Payment).where(Payment.provider_payment_id == str(provider_id))
        )).scalar_one_or_none()
        if payment is None:
            logging.warning("Ignoring YooKassa notification for unknown payment %s", provider_id)
            return web.json_response({"ok": True, "ignored": "unknown_payment"})

        if event == "payment.succeeded":
            activated = await check_and_activate(session, payment.idempotence_key)
            logging.info("YooKassa payment %s processed: activated=%s", provider_id, activated)
        elif payment.status not in {"succeeded", "canceled"}:
            payment.status = "canceled"
            if payment.idempotence_key.startswith("alter-renew-"):
                user = await session.get(User, payment.user_id, with_for_update=True)
                if user:
                    user.auto_renew = False
            await session.commit()

    return web.json_response({"ok": True})
