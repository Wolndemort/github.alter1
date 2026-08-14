"""Best-effort Expo push delivery for the mobile client."""

from __future__ import annotations

import logging
import uuid

import httpx
from data.database import async_session
from data.models import Notification


async def send_push(user, title: str, body: str) -> bool:
    notification_id = str(uuid.uuid4())
    try:
        async with async_session() as session:
            notification = Notification(
                id=notification_id,
                user_id=user.id,
                title=title[:80],
                body=body[:500],
                kind="push",
                route="notifications",
                data={"notification_id": notification_id},
            )
            session.add(notification)
            await session.commit()
    except Exception:
        logging.exception("Notification inbox write failed")
    token = str((user.tech_stack or {}).get("expo_push_token") or "").strip()
    if not token:
        return False
    payload = {
        "to": token,
        "title": title[:80],
        "body": body[:400],
        "sound": "default",
        "channelId": "alter",
        # The mobile client uses this payload to keep a tapped push visible in
        # the chat instead of silently dropping it into the currently open UI.
        "data": {"route": "notifications", "notification_id": notification_id},
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post("https://exp.host/--/api/v2/push/send", json=payload)
        if response.status_code >= 300:
            logging.warning("Expo push rejected status=%s", response.status_code)
            return False
        return True
    except Exception:
        logging.exception("Expo push delivery failed")
        return False
