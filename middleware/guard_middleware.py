"""One place for request admission: spam protection and daily quota."""
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from config import config
from utils.redis_store import charge_request, allow_request


class GuardMiddleware(BaseMiddleware):
    def __init__(self, redis, *, spam_limit: int | None = None, spam_window: int | None = None):
        super().__init__()
        self.redis = redis
        self.spam_limit = spam_limit or config.SPAM_REQUEST_LIMIT
        self.spam_window = spam_window or config.SPAM_WINDOW_SECONDS

    async def __call__(self, handler: Callable[..., Awaitable[Any]], event: TelegramObject, data: dict[str, Any]) -> Any:
        user = getattr(event, "from_user", None)
        if user is not None:
            data["billing_allowed"] = await charge_request(self.redis, user.id, config.DAILY_REQUEST_LIMIT)
            data["spam_allowed"] = await allow_request(self.redis, user.id, self.spam_limit, self.spam_window)
        return await handler(event, data)
