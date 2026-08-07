"""Best-effort Expo push delivery for the mobile client."""

from __future__ import annotations

import logging

import httpx


async def send_push(user, title: str, body: str) -> bool:
    token = str((user.tech_stack or {}).get("expo_push_token") or "").strip()
    if not token:
        return False
    payload = {"to": token, "title": title[:80], "body": body[:400], "sound": "default"}
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
