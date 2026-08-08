"""Plan-aware credit charging shared by HTTP and Telegram entrypoints."""

from data.database import async_session
from data.models import User
from utils.billing import credits_limit
from utils.redis_store import charge_credits


async def charge_user_credits(redis, user: User, cost: int) -> bool:
    """Atomically charge credits using the user's current subscription plan."""
    return await charge_credits(redis, user.id, cost, credits_limit(user))


async def charge_user_id_credits(redis, user_id: int, cost: int, session_factory=async_session) -> bool:
    """Load the account plan and charge against its matching quota."""
    async with session_factory() as session:
        user = await session.get(User, user_id)
        if user is None:
            return False
        return await charge_user_credits(redis, user, cost)
