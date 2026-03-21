import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import config
from data.database import async_session, engine, Base
from handlers.user_handlers import router
from middleware.db_middleware import DbSessionMiddleware
from utils.tasks import monitor_personality_imprint


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    )
    print("🚀 ALTER: Проверка и создание таблиц в базе...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ База данных готова!")

    bot = Bot(token=config.BOT_TOKEN.get_secret_value())
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.middleware(DbSessionMiddleware(session_pool=async_session))
    dp.include_router(router)

    asyncio.create_task(monitor_personality_imprint())

    print("🚀 ALTER: Система и фоновый анализ запущены!")
    print("🧠 База данных: подключена")
    print("🤖 Бот: активен")

    try:
        # Очистка очереди сообщений и запуск
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except Exception as e:
        logging.error(f"❌ Критическая ошибка при работе бота: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🔌 ALTER: Система деактивирована пользователем")
