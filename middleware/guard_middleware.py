"""One place for request admission: spam protection and daily quota."""
from typing import Any, Awaitable, Callable
import logging

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from redis.exceptions import RedisError

from config import config
from data.models import User
from utils.redis_store import charge_request, allow_request, charge_credits
from utils.billing import has_active_subscription, has_owner_access, is_owner, credits_limit
from services.account_linking import resolve_telegram_user
from utils.audio_actions import detect_audio_action
from utils.capabilities import is_capabilities_request
from utils.generation_intent import generation_kind


def _billing_exempt(event: TelegramObject) -> bool:
    text = getattr(event, "text", None) or ""
    command = text.split(maxsplit=1)[0].split("@", 1)[0].casefold() if text.startswith("/") else ""
    return command in {"/start", "/buy", "/status", "/help"}


def _legal_exempt(event: TelegramObject) -> bool:
    text = getattr(event, "text", None) or ""
    command = text.split(maxsplit=1)[0].split("@", 1)[0].casefold() if text.startswith("/") else ""
    return command == "/start"


def _credit_exempt(event: TelegramObject) -> bool:
    """Heavy handlers charge their exact operation after inspecting media."""
    if getattr(event, "voice", None) is not None or getattr(event, "photo", None) or getattr(event, "video", None):
        return True
    text = getattr(event, "text", None) or ""
    return bool(is_capabilities_request(text) or generation_kind(text) or detect_audio_action(text))


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
                # Resolve owner identity before touching Redis. Owners must not
                # consume daily quota, including through a linked Telegram account.
                db_session = data.get("db_session")
                linked_user = await resolve_telegram_user(db_session, user.id) if db_session is not None else None
                linked_email = getattr(data.get("db_user"), "email", None) or getattr(linked_user, "email", None)
                if db_session is not None and hasattr(db_session, "execute"):
                    from sqlalchemy import select
                    from data.models import WebAccount
                    account = (await db_session.execute(
                        select(WebAccount).where(WebAccount.telegram_user_id == user.id)
                    )).scalar_one_or_none()
                    linked_email = linked_email or getattr(account, "email", None)
                owner_access = has_owner_access(user.id, linked_email)
                data["owner_access"] = owner_access
                data["billing_allowed"] = True if (
                    owner_access or _billing_exempt(event) or
                    (linked_user is not None and not has_active_subscription(linked_user))
                ) else await charge_request(self.redis, user.id, config.DAILY_REQUEST_LIMIT)
            except RedisError:
                logging.exception("Redis billing check failed; blocking request")
                data["billing_allowed"] = False
            try:
                data["spam_allowed"] = await allow_request(self.redis, user.id, self.spam_limit, self.spam_window)
            except RedisError:
                logging.exception("Redis spam check failed; blocking request")
                data["spam_allowed"] = False
            db_user = linked_user if user is not None else None
            owner_access = data.get("owner_access", has_owner_access(user.id, getattr(db_user, "email", None)))
            db_session = data.get("db_session")
            if db_session is not None:
                db_user = await resolve_telegram_user(db_session, user.id)
                if (db_user is None or not db_user.legal_accepted_at) and not _legal_exempt(event):
                    answer = getattr(event, "answer", None)
                    if answer:
                        await answer("Сначала открой /start, ознакомься с документами и нажми «Принять и продолжить».")
                    return None
                if not owner_access:
                    data["subscription_allowed"] = has_active_subscription(db_user)
            if data.get("db_session") is not None and not owner_access and not _billing_exempt(event):
                answer = getattr(event, "answer", None)
                if not data["spam_allowed"]:
                    if answer:
                        await answer("Слишком много запросов подряд. Подожди немного и попробуй снова.")
                    return None
                if not data["billing_allowed"]:
                    if answer:
                        await answer("Дневной лимит запросов исчерпан. Попробуй завтра.")
                    return None
                subscription_allowed = has_active_subscription(db_user)
                data["subscription_allowed"] = subscription_allowed
                if not subscription_allowed and not _billing_exempt(event):
                    if answer:
                        await answer("Доступ ALTER приостановлен: trial или подписка закончились. Память, история и настройки сохранены. Продолжить можно через /buy на alterai.ru.")
                    return None
                if _credit_exempt(event):
                    data["credits_allowed"] = True
                else:
                    data["credits_allowed"] = await charge_credits(self.redis, user.id, 1, credits_limit(db_user))
                    if not data["credits_allowed"] and db_user is not None and int(db_user.credit_balance or 0) > 0:
                        db_user.credit_balance = int(db_user.credit_balance or 0) - 1
                        await db_session.commit()
                        data["credits_allowed"] = True
                if not data["credits_allowed"]:
                    if answer:
                        await answer("AI-квота и купленные пакеты закончились. Память и история сохранены — пополни баланс на alterai.ru или дождись обновления месячного лимита.")
                    return None
            if db_session is not None and owner_access:
                data["subscription_allowed"] = True
        try:
            return await handler(event, data)
        except Exception:
            # Do not leave the user without feedback when an unexpected error
            # happens after admission (DB, model, Telegram, or application code).
            logging.exception("Unhandled bot handler error")
            answer = getattr(event, "answer", None)
            if answer:
                try:
                    await answer("Не смог обработать сообщение. Попробуй ещё раз через несколько секунд.")
                except Exception:
                    logging.exception("Failed to send handler error reply")
            return None
