import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from aiohttp import web

from config import config
from data.database import async_session, engine
from handlers.user_handlers import router
from middleware.db_middleware import DbSessionMiddleware
from middleware.guard_middleware import GuardMiddleware
from utils.redis_store import create_redis, close_redis
from utils.runtime import check_dependencies
from utils.tasks import monitor_checkins, monitor_memory_cleanup, monitor_personality_imprint, monitor_reminders, monitor_subscription_renewals, monitor_subscription_expiry_reminders
from utils.payment_webhook import handle_yookassa_webhook


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
    logging.info("ALTER: starting database and background tasks")
    bot = Bot(token=config.BOT_TOKEN.get_secret_value())
    redis = create_redis()
    if not await check_dependencies(redis, engine):
        logging.error("ALTER остановлен до polling: запусти зависимости или проверь .env")
        await close_redis(redis)
        await bot.session.close()
        return
    dispatcher = Dispatcher(storage=RedisStorage(redis=redis))
    dispatcher.message.middleware(DbSessionMiddleware(session_pool=async_session))
    dispatcher.callback_query.middleware(DbSessionMiddleware(session_pool=async_session))
    dispatcher.message.middleware(GuardMiddleware(redis))
    dispatcher.include_router(router)
    web_app = web.Application()
    web_app.router.add_get("/health", lambda request: web.json_response({"ok": True}))
    web_app.router.add_post(config.PAYMENT_WEBHOOK_PATH, handle_yookassa_webhook)
    web_runner = web.AppRunner(web_app)
    await web_runner.setup()
    web_site = web.TCPSite(web_runner, config.PAYMENT_WEBHOOK_HOST, config.PAYMENT_WEBHOOK_PORT)
    await web_site.start()
    logging.info("Payment webhook listening on %s:%s%s", config.PAYMENT_WEBHOOK_HOST, config.PAYMENT_WEBHOOK_PORT, config.PAYMENT_WEBHOOK_PATH)
    asyncio.create_task(monitor_personality_imprint())
    asyncio.create_task(monitor_memory_cleanup())
    asyncio.create_task(monitor_reminders(bot))
    asyncio.create_task(monitor_checkins(bot))
    asyncio.create_task(monitor_subscription_renewals(bot))
    asyncio.create_task(monitor_subscription_expiry_reminders(bot))
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logging.info("ALTER is running")
        await dispatcher.start_polling(bot)
    except Exception:
        logging.exception("Critical bot runtime error")
    finally:
        await web_runner.cleanup()
        await close_redis(redis)
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("ALTER stopped by user")
