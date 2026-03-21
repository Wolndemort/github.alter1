from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified
from utils.helpers import deep_merge
from data.models import Session
from data.database import async_session, engine
from utils.ap_logic import summarize_session


async def monitor_personality_imprint():
    """Фоновая задача: ищет сессии, которые не обновлялись 20 минут"""
    while True:
        async with async_session() as db:
            print(f"🔍 TASKS DEBUG: Подключение к {engine.url}")
            threshold = datetime.utcnow() - timedelta(minutes=5)
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
                            # 1. Берем текущую память (копируем, чтобы SQLAlchemy видела изменения)
                            current_memory = dict(user.memory) if user.memory else {}

                            # 2. ПРИМЕНЯЕМ DEEP MERGE (вместо обычного update)
                            updated_memory = deep_merge(current_memory, new_facts)

                            user.memory = updated_memory
                            session.is_processed = True

                            flag_modified(user, "memory")

                            print(f"✅ ALTER: Слепок личности обновлен для {user.first_name}")
                        else:
                            print(f"⚠️ ALTER: Новых фактов не найдено в сессии {session.id}")

                            session.is_processed = True

                    except Exception as e:
                        print(f"❌ Ошибка при обработке сессии {session.id}: {e}")
