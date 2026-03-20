from datetime import datetime

from aiogram import Router, types
from aiogram.filters import CommandStart
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from data.models import User, Session

router = Router()


@router.message(CommandStart)
async def cmd_start(message: types.Message, db_session: AsyncSession):
    user = await db_session.get(User, message.from_user.id)
    if not user:
        user = User(
            id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            memory={},
            tech_stack={})

        db_session.add(user)
        await db_session.commit()
        await message.answer(f"Привет, {message.from_user.first_name}! "
                             f"Я — ALTER. Твоя память теперь в безопасности. Начинай писать, я всё запомню.")
    else:
        await message.answer(f"С возвращением, {user.first_name}! Я готов продолжить наш цифровой след.")


@router.message()
async def handle_any_message(message: types.Message, db_session: AsyncSession):
    """
    Хендлер для сохранения всех входящих сообщений в raw_messages.
    """
    if not message.text:
        return

    stmt = select(Session).where(
        Session.user_id == message.from_user.id,
        Session.is_processed.is_(False),
    ).order_by(Session.started_at.desc())

    result = await db_session.execute(stmt)
    session = result.scalar_one_or_none()

    if not session:
        session = Session(user_id=message.from_user.id, raw_messages=[])
        db_session.add(session)
        await db_session.flush()

    new_msg = {
        "role": "user",
        "content": message.text,
        "timestamp": datetime.now().isoformat()
    }

    updated_messages = list(session.raw_messages)
    updated_messages.append(new_msg)
    session.raw_messages = updated_messages
    print(f"🛠 DEBUG: Сохраняю сообщение в сессию {session.id if session.id else 'NEW'}")
    try:
        await db_session.commit()
        await db_session.refresh(session)
        print(f"✅ DEBUG: Сессия {session.id} успешно сохранена в Postgres!")
    except Exception as e:
        print(f"❌ DEBUG ОШИБКА СОХРАНЕНИЯ: {e}")

