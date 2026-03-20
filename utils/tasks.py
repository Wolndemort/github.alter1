import asyncio
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from data.models import Session
from data.database import async_session, engine
from utils.ap_logic import summarize_session


async def monitor_personality_imprint():
    """Фоновая задача: ищет сессии, которые не обновлялись 20 минут"""
    while True:
        async with async_session() as db:
            print(f"🔍 TASKS DEBUG: Подключение к {engine.url}")
            threshold = datetime.now() - timedelta(minutes=5)
            stmt = select(Session).where(Session.is_processed.is_(False), Session.updated_at < threshold).options(
                selectinload(Session.user))
            result = await db.execute(stmt)
            session_to_process = result.scalars().all()
            all_sessions = await db.execute(select(Session))
            print(f"DEBUG: Всего сессий в базе: {len(all_sessions.scalars().all())}")
            print(f"DEBUG: Используемый порог времени: {threshold}")
            if not session_to_process:
                pass
            else:
                for session in session_to_process:
                    try:
                        print(f"🧠 ALTER: Начинаю анализ сессии {session.id} для юзера {session.user_id}...")
                        new_facts = await summarize_session(session.raw_messages)
                        user = session.user
                        if new_facts and user:
                            current_memory = dict(user.memory) or {}
                            current_memory.update(new_facts)
                            user.memory = current_memory
                            session.is_processed = True
                            flag_modified(user, "memory")
                            print(f"✅ ALTER: Слепок личности обновлен для {user.first_name}")
                        else:
                            print(f"⚠️ ALTER: Gemini не нашел новых фактов в сессии {session.id}")

                    except Exception as e:
                        print(f"❌ Ошибка при обработке сессии {session.id}: {e}")
                try:
                    await db.commit()
                    print(f"🚀 Все изменения успешно сохранены в базу")
                except Exception as e:
                    await db.rollback()
                    print(f"❌ Ошибка при сохранении транзакции: {e}")
        await asyncio.sleep(60)
