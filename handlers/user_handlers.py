from datetime import datetime

from aiogram import Router, types
from aiogram.filters import CommandStart
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from data.models import User, Session

router = Router()


@router.message(CommandStart())
async def cmd_start(message: types.Message, db_session: AsyncSession):
    print(f"🔍 Ищу юзера {message.from_user.id}...")
    user = await db_session.get(User, message.from_user.id)

    if not user:
        print("🆕 Юзер не найден, создаю...")
        user = User(
            id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            memory={},
            tech_stack={}
        )
        db_session.add(user)
        try:
            await db_session.commit()
            print("✅ Юзер успешно СОХРАНЕН в базу!")
            await message.answer(f"Привет, {message.from_user.first_name}! Твоя память теперь в безопасности.")
        except Exception as e:
            await db_session.rollback()
            print(f"❌ ОШИБКА ПРИ КОММИТЕ: {e}")
            await message.answer("Ошибка при регистрации в базе данных.")
    else:
        print(f"👋 Юзер {user.first_name} уже в базе.")
        await message.answer(f"С возвращением, {user.first_name}!")


@router.message()
async def handle_any_message(message: types.Message, db_session: AsyncSession):
    """
    Хендлер для сохранения всех входящих сообщений в raw_messages.
    """
    print(f"📩 ПОЛУЧЕНО СООБЩЕНИЕ: {message.text}")
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
        "timestamp": datetime.utcnow().isoformat()
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

