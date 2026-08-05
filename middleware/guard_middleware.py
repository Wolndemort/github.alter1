"""One place for request admission: spam protection and daily quota."""
from typing import Any, Awaitable, Callable
import logging

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from redis.exceptions import RedisError

from config import config
from data.models import User
from utils.redis_store import charge_request, allow_request
from utils.billing import has_active_subscription, is_owner


def _billing_exempt(event: TelegramObject) -> bool:
    text = getattr(event, "text", None) or ""
    command = text.split(maxsplit=1)[0].split("@", 1)[0].casefold() if text.startswith("/") else ""
    return command in {"/start", "/buy", "/status", "/help"}


class GuardMiddleware(BaseMiddleware):
    def __init__(self, redis, *, spam_limit: int | None = None, spam_window: int | None = None):
        super().__init__()
        self.redis = redis
        self.spam_limit = spam_limit or config.SPAM_REQUEST_LIMIT
        self.spam_window = spam_window or config.SPAM_WINDOW_SECONDS

    async def __call__(self, handler: Callable[..., Awaitable[Any]], event: TelegramObject, data: dict[str, Any]) -> Any:
        user = getattr(event, "from_user", None)
        if user is not None:
            try:
                data["billing_allowed"] = await charge_request(self.redis, user.id, config.DAILY_REQUEST_LIMIT)
            except RedisError:
                logging.exception("Redis billing check failed; allowing request")
                data["billing_allowed"] = True
            try:
                data["spam_allowed"] = await allow_request(self.redis, user.id, self.spam_limit, self.spam_window)
            except RedisError:
                logging.exception("Redis spam check failed; allowing request")
                data["spam_allowed"] = True
            db_session = data.get("db_session")
            if db_session is not None and not is_owner(user.id):
                db_user = await db_session.get(User, user.id)
                subscription_allowed = has_active_subscription(db_user)
                data["subscription_allowed"] = subscription_allowed
                if not subscription_allowed and not _billing_exempt(event):
                    answer = getattr(event, "answer", None)
                    if answer:
                        await answer("Доступ ALTER доступен после оплаты подписки на 30 дней. Используй /buy, чтобы оплатить.")
                    return None
            else:
                data["subscription_allowed"] = True
        return await handler(event, data)
