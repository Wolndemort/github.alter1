import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage

from config import config
from data.database import async_session
from handlers.user_handlers import router
from middleware.db_middleware import DbSessionMiddleware
from middleware.guard_middleware import GuardMiddleware
from utils.redis_store import create_redis, close_redis
from utils.tasks import monitor_checkins, monitor_personality_imprint, monitor_reminders


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
    logging.info("ALTER: starting database and background tasks")
    bot = Bot(token=config.BOT_TOKEN.get_secret_value())
    redis = create_redis()
    dispatcher = Dispatcher(storage=RedisStorage(redis=redis))
    dispatcher.message.middleware(DbSessionMiddleware(session_pool=async_session))
    dispatcher.message.middleware(GuardMiddleware(redis))
    dispatcher.include_router(router)
    asyncio.create_task(monitor_personality_imprint())
    asyncio.create_task(monitor_reminders(bot))
    asyncio.create_task(monitor_checkins(bot))
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logging.info("ALTER is running")
        await dispatcher.start_polling(bot)
    except Exception:
        logging.exception("Critical bot runtime error")
    finally:
        await close_redis(redis)
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("ALTER stopped by user")
