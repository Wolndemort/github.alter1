from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from config import config
from utils.redis_store import charge_request


class BillingMiddleware(BaseMiddleware):
    def __init__(self, redis):
        super().__init__()
        self.redis = redis

    async def __call__(self, handler: Callable, event: TelegramObject, data: dict[str, Any]) -> Any:
        user = getattr(event, "from_user", None)
        if user is not None:
            data["billing_allowed"] = await charge_request(self.redis, user.id, config.DAILY_REQUEST_LIMIT)
        return await handler(event, data)
