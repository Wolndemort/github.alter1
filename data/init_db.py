import asyncio
import logging
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from data.database import engine, Base
from data.models import User, Session


async def init_db():
    async with engine.begin() as conn:
        print('🚀 Инициализация таблиц в Docker...')
        await conn.run_sync(Base.metadata.create_all)
        print("✅ База данных ALTER готова к работе!")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(init_db())
    except Exception as e:
        print(f"❌ Ошибка: {e}")