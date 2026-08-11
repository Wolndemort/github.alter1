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
from utils.redis_store import create_redis, close_redis, allow_http_request, charge_request
from utils.billing import is_owner
from services.auth_service import verify_token
from redis.exceptions import RedisError
from utils.runtime import check_dependencies
from utils.tasks import monitor_checkins, monitor_memory_cleanup, monitor_personality_imprint, monitor_reminders, monitor_subscription_renewals, monitor_subscription_expiry_reminders
from utils.payment_webhook import handle_yookassa_webhook
from api.auth_routes import setup_auth_routes
from api.chat_routes import setup_chat_routes
from api.user_features_routes import setup_user_features_routes
from api.youtube_routes import setup_youtube_routes
from api.elevenlabs_routes import setup_elevenlabs_routes
from api.calendar_routes import setup_calendar_routes
from api.faq_routes import setup_faq_routes
from utils.sentry_setup import init_sentry


async def main():
    init_sentry()
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
    dispatcher["redis"] = redis
    dispatcher.message.middleware(DbSessionMiddleware(session_pool=async_session))
    dispatcher.callback_query.middleware(DbSessionMiddleware(session_pool=async_session))
    dispatcher.message.middleware(GuardMiddleware(redis))
    dispatcher.include_router(router)
    web_app = web.Application()

    @web.middleware
    async def http_rate_limit(request, handler):
        if request.path.startswith("/api/") and request.path not in {"/api/v1/usage"}:
            remote = request.remote or "unknown"
            try:
                if not await allow_http_request(redis, remote, config.HTTP_RATE_LIMIT, config.HTTP_RATE_WINDOW_SECONDS):
                    raise web.HTTPTooManyRequests(text="too many requests")
            except web.HTTPTooManyRequests:
                raise
            except Exception:
                logging.exception("HTTP rate limiter unavailable")
                raise web.HTTPServiceUnavailable(text="rate limiter unavailable")
            expensive = request.path.startswith(("/api/v1/chat/", "/api/v1/audio/", "/api/v1/youtube/", "/api/v1/media/"))
            header = request.headers.get("Authorization", "")
            if expensive and header.startswith("Bearer ") and config.APP_AUTH_SECRET:
                try:
                    user_id = verify_token(header[7:].strip(), config.APP_AUTH_SECRET.get_secret_value())
                    if not is_owner(user_id) and not await charge_request(redis, user_id, config.DAILY_REQUEST_LIMIT):
                        raise web.HTTPTooManyRequests(text="daily request limit reached")
                except web.HTTPTooManyRequests:
                    raise
                except (RedisError, ValueError):
                    logging.exception("Authenticated HTTP quota check failed")
                    raise web.HTTPServiceUnavailable(text="quota service unavailable")
        return await handler(request)

    web_app.middlewares.append(http_rate_limit)

    async def health(request):
        return web.json_response({"ok": True, "service": "alter"})

    async def readiness(request):
        if not await check_dependencies(redis, engine):
            raise web.HTTPServiceUnavailable(text="dependencies unavailable")
        return web.json_response({"ok": True, "ready": True})

    web_app.router.add_get("/health", health)
    web_app.router.add_get("/ready", readiness)
    web_app.router.add_post(config.PAYMENT_WEBHOOK_PATH, handle_yookassa_webhook)
    setup_auth_routes(web_app)
    setup_chat_routes(web_app)
    setup_user_features_routes(web_app)
    setup_youtube_routes(web_app)
    setup_elevenlabs_routes(web_app)
    setup_calendar_routes(web_app)
    setup_faq_routes(web_app)
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
