from datetime import datetime, timedelta, timezone

from aiogram import F, Router, types
from aiogram.types import BufferedInputFile
from aiogram.filters import Command, CommandStart
from aiogram.filters.command import CommandObject
from sqlalchemy import delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from data.models import ImportantEvent, Reminder, User, Session
from utils.ap_logic import generate_reply
from utils.media_logic import generate_media_reply
from utils.media import video_audio, video_duration, video_preview
from io import BytesIO
from utils.youtube_search import search_youtube
from utils.web_search import search_web
from utils.audio_search import download_audio, remove_audio
from utils.weather import get_weather, is_weather_request, parse_weather_city
from utils.marketplace_links import format_marketplace_links
from utils.keyboards import memory_keyboard, memory_categories_keyboard, voice_keyboard, VOICE_BUTTON, VOICE_ON_BUTTON, VOICE_OFF_BUTTON
from utils.reminders import parse_reminder, parse_time_answer
from utils.voice import transcribe_voice
from utils.tts import synthesize_speech
from utils.vector_memory import recall, remember
from utils.tasks import process_session
from utils.intent import explicit_memory_fact, is_youtube_request, should_search_web, youtube_query
from sqlalchemy.orm.attributes import flag_modified
from config import config
import logging

router = Router()


def voice_enabled(user: User) -> bool:
    return (user.tech_stack or {}).get("voice_replies", config.VOICE_REPLY_DEFAULT)


async def answer_reply(message: types.Message, reply: str, user: User, force_voice: bool = False):
    """Send text and, when enabled, a voice copy. TTS failure never hides the text."""
    await message.answer(reply)
    if force_voice or voice_enabled(user):
        audio = await synthesize_speech(reply)
        if audio:
            await message.answer_voice(BufferedInputFile(audio, filename="alter.ogg"))


@router.message(Command("voice_on"))
async def cmd_voice_on(message: types.Message, db_session: AsyncSession):
    user = await get_or_create_user(message, db_session)
    settings = dict(user.tech_stack or {})
    settings["voice_replies"] = True
    user.tech_stack = settings
    await db_session.commit()
    await message.answer("Голосовые ответы включены.")


@router.message(Command("voice_off"))
async def cmd_voice_off(message: types.Message, db_session: AsyncSession):
    user = await get_or_create_user(message, db_session)
    settings = dict(user.tech_stack or {})
    settings["voice_replies"] = False
    user.tech_stack = settings
    await db_session.commit()
    await message.answer("Голосовые ответы выключены.")


@router.message(Command("voice"))
async def cmd_voice(message: types.Message, db_session: AsyncSession):
    user = await get_or_create_user(message, db_session)
    text = message.text.partition(" ")[2].strip()
    if not text:
        await message.answer("Формат: /voice текст, на который нужен голосовой ответ")
        return
    audio = await synthesize_speech(text)
    if audio:
        await message.answer_voice(BufferedInputFile(audio, filename="alter.ogg"))
    else:
        await message.answer("Не удалось создать голосовой ответ, попробуй ещё раз.")

@router.message(F.text == "🧠 Память")
async def button_memory(message: types.Message, db_session: AsyncSession):
    await cmd_memory(message, db_session)


@router.message(F.text == "🆕 Новый разговор")
async def button_new_session(message: types.Message, db_session: AsyncSession):
    await cmd_new_session(message, db_session)


@router.message(F.text == "⏰ Напоминания")
async def button_reminders(message: types.Message, db_session: AsyncSession):
    await cmd_reminders(message, db_session)


@router.message(F.text == "💭 Check-in")
async def button_checkins(message: types.Message, db_session: AsyncSession):
    await message.answer("Выбери режим: /checkins_on или /checkins_off", reply_markup=memory_keyboard())


@router.message(F.text == "⚙️ Настройки")
async def button_settings(message: types.Message):
    await message.answer("Настройки памяти: выбери категорию для удаления или используй /clear_memory.", reply_markup=memory_categories_keyboard())


@router.message(F.text == VOICE_BUTTON)
async def button_voice(message: types.Message):
    await message.answer("Настройка голосовых ответов:", reply_markup=voice_keyboard())


@router.message(F.text == VOICE_ON_BUTTON)
async def button_voice_on(message: types.Message, db_session: AsyncSession):
    await cmd_voice_on(message, db_session)


@router.message(F.text == VOICE_OFF_BUTTON)
async def button_voice_off(message: types.Message, db_session: AsyncSession):
    await cmd_voice_off(message, db_session)


@router.message(F.text == "❓ Помощь")
async def button_help(message: types.Message):
    await cmd_help(message)


@router.message(F.text == "⬅️ Назад")
async def button_back(message: types.Message):
    await message.answer("Главное меню", reply_markup=memory_keyboard())


@router.message(F.text.in_({"identity", "goals_habits", "skills_career", "interests_hobbies", "open_loops"}))
async def button_forget_category(message: types.Message, command: CommandObject, db_session: AsyncSession):
    await cmd_forget(message, CommandObject(args=message.text), db_session)


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "ALTER умеет:\n"
        "• отвечать на сообщения и помнить важные факты\n"
        "• анализировать фото и короткие видео\n"
        "• расшифровывать голосовые\n"
        "• ставить напоминания: /remind 2026-08-04 10:00 текст\n"
        "• делать check-in и спрашивать, как всё прошло\n\n"
        "Команды памяти: /memory, /forget, /clear_memory, /new_session\n"
        "Check-in: /checkins_on или /checkins_off"
    )


@router.message(lambda message: message.voice is not None)
async def handle_voice(message: types.Message, db_session: AsyncSession):
    try:
        buffer = await message.bot.download(message.voice, destination=BytesIO())
        text = await transcribe_voice(buffer.getvalue())
        if not text:
            await message.answer("Не смог разобрать голосовое сообщение.")
            return
        user = await get_or_create_user(message, db_session)
        session = await get_active_session(user.id, db_session)
        if session is None:
            session = Session(user_id=user.id, raw_messages=[])
            db_session.add(session)
            await db_session.flush()
        append_session_message(session, "user", text)
        # Расшифровка используется только внутри ALTER и не отправляется пользователю.
        await message.bot.send_chat_action(message.chat.id, "typing")
        lowered = text.lower()
        music_words = ("музык", "песн", "трек", "альбом", "исполнитель", "ютуб", "youtube", "послуш")
        audio_words = ("включи", "пришли песню", "отправь песню", "скачай песню", "скинь песню", "аудио")
        if any(word in lowered for word in music_words) and any(word in lowered for word in audio_words):
            results = await search_youtube(youtube_query(text))
            if results:
                downloaded = await download_audio(results[0]["url"])
                if downloaded:
                    audio_file, audio_title = downloaded
                    try:
                        from aiogram.types import FSInputFile
                        await message.answer_audio(FSInputFile(str(audio_file)), title=audio_title[:64], performer=results[0].get("channel", ""))
                    finally:
                        remove_audio(audio_file)
                    append_session_message(session, "assistant", f"Отправил аудио: {audio_title}")
                    await db_session.commit()
                    return
        reply = await generate_reply(
            recent_context(session.raw_messages), dict(user.memory or {})
        )
        # Respect the user's voice setting for replies to voice messages too.
        await answer_reply(message, reply, user)
        append_session_message(session, "assistant", reply)
        await db_session.commit()
    except Exception:
        logging.exception("Voice message handling failed")
        await message.answer("Не удалось обработать голосовое сообщение.")


@router.message(lambda message: message.photo or message.video)
async def handle_media(message: types.Message, db_session: AsyncSession):
    prompt = message.caption or "Проанализируй это изображение и объясни, что на нём."
    try:
        if message.photo:
            buffer = await message.bot.download(message.photo[-1], destination=BytesIO())
            media = [("image/jpeg", buffer.getvalue())]
        else:
            if message.video.file_size and message.video.file_size > 20 * 1024 * 1024:
                await message.answer("Видео слишком большое. Пришли ролик до 20 МБ.")
                return
            buffer = await message.bot.download(message.video, destination=BytesIO())
            video_data = buffer.getvalue()
            duration = await video_duration(video_data)
            if duration and duration > 180:
                await message.answer("Видео длиннее 3 минут. Пришли короткий фрагмент.")
                return
            media = await video_preview(video_data)
            if not media:
                await message.answer("Не удалось извлечь кадры из видео.")
                return
            audio = await video_audio(video_data)
            if audio:
                transcript = await transcribe_voice(audio)
                if transcript:
                    prompt += f"\n\nРасшифровка речи в видео:\n{transcript}"
        await message.bot.send_chat_action(message.chat.id, "typing")
        reply = await generate_media_reply(prompt, media)
        await message.answer(reply)
        user = await get_or_create_user(message, db_session)
        session = await get_active_session(user.id, db_session)
        if session is None:
            session = Session(user_id=user.id, raw_messages=[])
            db_session.add(session)
        kind = "Фото" if message.photo else "Видео"
        append_session_message(session, "user", f"[{kind}] {prompt}")
        append_session_message(session, "assistant", reply)
        await db_session.commit()
    except Exception:
        await message.answer("Не удалось обработать этот файл.")


def format_memory(memory: dict) -> str:
    if not memory:
        return "🧠 Пока ALTER ничего важного о тебе не помнит."
    lines = ["🧠 Что ALTER помнит о тебе:"]
    for category, facts in memory.items():
        if not facts:
            continue
        if isinstance(facts, dict):
            value = "; ".join(f"{key}: {item}" for key, item in facts.items())
        elif isinstance(facts, list):
            value = ", ".join(str(item) for item in facts)
        else:
            value = str(facts)
        lines.append(f"• {category}: {value}")
    return "\n".join(lines) if len(lines) > 1 else "🧠 Пока ALTER ничего важного о тебе не помнит."


async def get_active_session(user_id: int, db_session: AsyncSession) -> Session | None:
    result = await db_session.execute(select(Session).where(
        Session.user_id == user_id, Session.is_processed.is_(False)
    ).options(selectinload(Session.user)).order_by(Session.started_at.desc()))
    return result.scalar_one_or_none()


def append_session_message(session: Session, role: str, content: str) -> None:
    """Append a user or assistant turn to the short-term transcript."""
    messages = list(session.raw_messages or [])
    messages.append({"role": role, "content": content, "timestamp": datetime.utcnow().isoformat()})
    session.raw_messages = messages


def recent_context(messages: list, limit: int = 40) -> list:
    return list(messages[-limit:])


async def get_or_create_user(message: types.Message, db_session: AsyncSession) -> User:
    user = await db_session.get(User, message.from_user.id)
    if user is None:
        user = User(id=message.from_user.id,
                    username=message.from_user.username,
                    first_name=message.from_user.first_name or "Пользователь",
                    memory={}, tech_stack={})
        db_session.add(user)
        await db_session.flush()
    return user


@router.message(CommandStart())
async def cmd_start_welcome(message: types.Message, db_session: AsyncSession):
    user = await get_or_create_user(message, db_session)
    await db_session.commit()
    name = message.from_user.first_name or "друг"
    text = (
        f"✨ <b>Привет, {name}!</b>\n\n"
        "Я — <b>ALTER</b>, персональный искусственный интеллект "
        "с долгосрочной памятью.\n\n"
        "Я могу помнить важные факты о тебе, помогать с задачами, "
        "анализировать фото и голосовые сообщения, ставить напоминания "
        "и поддерживать разговор с учётом контекста.\n\n"
        "💡 Просто напиши, что тебе нужно.\n"
        "Например: <i>«Запомни, что я изучаю Python»</i>\n\n"
        "🧠 Управление памятью: кнопка «Память» или команда /memory\n"
        "❓ Все возможности — /help"
    )
    await message.answer(text, reply_markup=memory_keyboard(), parse_mode="HTML")


@router.message(Command("memory"))
async def cmd_memory(message: types.Message, db_session: AsyncSession):
    user = await get_or_create_user(message, db_session)
    text = format_memory(user.memory or {})
    # Telegram rejects messages longer than 4096 characters.
    chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)] or [text]
    for index, chunk in enumerate(chunks):
        await message.answer(
            chunk,
            reply_markup=memory_keyboard() if index == len(chunks) - 1 else None,
        )


@router.message(Command("forget"))
async def cmd_forget(message: types.Message, command: CommandObject, db_session: AsyncSession):
    category = (command.args or "").strip().lower()
    if not category:
        await message.answer("Укажи категорию, например: /forget skills_career", reply_markup=memory_keyboard())
        return
    user = await get_or_create_user(message, db_session)
    memory = dict(user.memory or {})
    if category not in memory:
        await message.answer(f"Категория «{category}» не найдена в памяти.", reply_markup=memory_keyboard())
        return
    memory.pop(category)
    user.memory = memory
    await db_session.commit()
    await message.answer(f"Забыл категорию «{category}».", reply_markup=memory_keyboard())


@router.message(Command("clear_memory"))
async def cmd_clear_memory(message: types.Message, db_session: AsyncSession):
    user = await get_or_create_user(message, db_session)
    user.memory = {}
    await db_session.execute(delete(ImportantEvent).where(ImportantEvent.user_id == user.id))
    await db_session.commit()
    await message.answer("Долгосрочная память очищена.", reply_markup=memory_keyboard())


@router.message(Command("new_session"))
async def cmd_new_session(message: types.Message, db_session: AsyncSession):
    user = await get_or_create_user(message, db_session)
    session = await get_active_session(user.id, db_session)
    if session:
        await process_session(session, db_session)
    await db_session.commit()
    await message.answer("Новый разговор начат.", reply_markup=memory_keyboard())


@router.message(Command("checkins_on"))
async def cmd_checkins_on(message: types.Message, db_session: AsyncSession):
    user = await get_or_create_user(message, db_session)
    user.checkins_enabled = True
    await db_session.commit()
    await message.answer("Мягкие check-in включены.", reply_markup=memory_keyboard())


@router.message(Command("checkins_off"))
async def cmd_checkins_off(message: types.Message, db_session: AsyncSession):
    user = await get_or_create_user(message, db_session)
    user.checkins_enabled = False
    await db_session.commit()
    await message.answer("Мягкие check-in выключены.", reply_markup=memory_keyboard())


@router.message(Command("remind"))
async def cmd_remind(message: types.Message, command: CommandObject, db_session: AsyncSession):
    """Create a simple one-time reminder: /remind 2026-08-04 10:00 text."""
    parts = (command.args or "").split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Формат: /remind 2026-08-04 10:00 текст", reply_markup=memory_keyboard())
        return
    try:
        remind_at = datetime.strptime(f"{parts[0]} {parts[1]}", "%Y-%m-%d %H:%M")
        remind_at = remind_at.replace(tzinfo=timezone(timedelta(hours=3)))
    except ValueError:
        await message.answer("Дата должна быть в формате 2026-08-04 10:00.", reply_markup=memory_keyboard())
        return
    if remind_at <= datetime.now(timezone.utc):
        await message.answer("Это время уже прошло.", reply_markup=memory_keyboard())
        return
    user = await get_or_create_user(message, db_session)
    db_session.add(Reminder(user_id=user.id, remind_at=remind_at, follow_up_at=remind_at + timedelta(hours=2), text=parts[2][:500]))
    await db_session.commit()
    await message.answer(f"Напомню {parts[0]} в {parts[1]}: {parts[2]}", reply_markup=memory_keyboard())


@router.message(Command("reminders"))
async def cmd_reminders(message: types.Message, db_session: AsyncSession):
    result = await db_session.execute(select(Reminder).where(
        Reminder.user_id == message.from_user.id,
        Reminder.is_sent.is_(False),
    ).order_by(Reminder.remind_at))
    reminders = result.scalars().all()
    if not reminders:
        await message.answer("Активных напоминаний нет.")
        return
    lines = ["Активные напоминания:"]
    for reminder in reminders:
        lines.append(f"#{reminder.id} — {reminder.remind_at:%d.%m %H:%M} — {reminder.text}")
    await message.answer("\n".join(lines))


@router.message(Command("cancel_reminder"))
async def cmd_cancel_reminder(message: types.Message, command: CommandObject, db_session: AsyncSession):
    try:
        reminder_id = int((command.args or "").strip())
    except ValueError:
        await message.answer("Формат: /cancel_reminder ID")
        return
    result = await db_session.execute(select(Reminder).where(
        Reminder.id == reminder_id, Reminder.user_id == message.from_user.id,
        Reminder.is_sent.is_(False),
    ))
    reminder = result.scalar_one_or_none()
    if not reminder:
        await message.answer("Активное напоминание не найдено.")
        return
    await db_session.delete(reminder)
    await db_session.commit()
    await message.answer(f"Напоминание #{reminder_id} отменено.")


@router.message(lambda message: message.text and is_weather_request(message.text) and not message.text.startswith("/weather"))
async def natural_weather(message: types.Message):
    city = parse_weather_city(message.text)
    result = await get_weather(city)
    await message.answer(result or "Не удалось получить погоду. Попробуй указать город.")


@router.message(Command("weather"))
async def cmd_weather(message: types.Message):
    city = message.text.partition(" ")[2].strip() or "Москва"
    result = await get_weather(city)
    await message.answer(result or "Не удалось получить погоду. Попробуй указать город.")


@router.message()
async def handle_any_message(message: types.Message, db_session: AsyncSession, billing_allowed: bool = True, spam_allowed: bool = True):
    """
    Хендлер для сохранения всех входящих сообщений в raw_messages.
    """
    print(f"📩 ПОЛУЧЕНО СООБЩЕНИЕ: {message.text}")
    if not message.text or not message.from_user:
        return
    if not spam_allowed:
        await message.answer("Слишком много сообщений подряд. Подожди немного и попробуй ещё раз.")
        return
    if not billing_allowed:
        await message.answer("Дневной лимит запросов исчерпан. Попробуй завтра.")
        return

    user = await get_or_create_user(message, db_session)
    explicit_fact = explicit_memory_fact(message.text)
    if explicit_fact:
        memory = dict(user.memory or {})
        category = "identity" if any(word in explicit_fact.casefold() for word in ("машин", "авто", "автомобил", "bmw", "mercedes", "лада")) else "preferences"
        values = dict(memory.get(category) or {})
        facts = list(values.get("explicit_facts") or [])
        if explicit_fact not in facts:
            facts.append(explicit_fact)
        values["explicit_facts"] = facts[-20:]
        memory[category] = values
        user.memory = memory
        flag_modified(user, "memory")
    if False:  # billing is handled by RedisBillingMiddleware
        await message.answer("Дневной лимит запросов исчерпан. Попробуй завтра.")
        return
    pending = user.pending_reminder or {}
    if pending:
        remind_at = parse_time_answer(message.text)
        if remind_at:
            db_session.add(Reminder(user_id=user.id, remind_at=remind_at, follow_up_at=remind_at + timedelta(hours=2), text=pending["text"][:500]))
            user.pending_reminder = {}
            await db_session.commit()
            await message.answer(f"Хорошо, напомню {remind_at.strftime('%d.%m в %H:%M')}: {pending['text']}")
            return

    parsed_reminder = parse_reminder(message.text)
    if parsed_reminder:
        remind_at, reminder_text = parsed_reminder
        db_session.add(Reminder(user_id=user.id, remind_at=remind_at, follow_up_at=remind_at + timedelta(hours=2), text=reminder_text[:500]))
        await db_session.commit()
        await message.answer(f"Записал. Напомню {remind_at.strftime('%d.%m в %H:%M')}: {reminder_text}")
        return

    if any(word in message.text.lower() for word in ("завтра", "сегодня", "пойду", "иду", "буду")):
        db_session.add(Reminder(
            user_id=user.id,
            kind="checkin",
            remind_at=datetime.now(timezone.utc) + timedelta(days=1),
            text=message.text.strip(),
        ))
        await db_session.commit()
        await message.answer("Понял. Завтра спрошу, как всё прошло — без отдельного напоминания.")
        return

    user = await get_or_create_user(message, db_session)

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

    append_session_message(session, "user", message.text)
    updated_messages = list(session.raw_messages)
    print(f"🛠 DEBUG: Сохраняю сообщение в сессию {session.id if session.id else 'NEW'}")
    await message.bot.send_chat_action(message.chat.id, "typing")
    search_results = []
    web_results = []
    audio_sent = False
    youtube_requested = is_youtube_request(message.text)
    music_words = ("музык", "песн", "трек", "альбом", "исполнитель", "ютуб", "youtube", "послуш")
    if any(word in message.text.lower() for word in music_words):
        search_results = await search_youtube(youtube_query(message.text))
    audio_words = ("включи", "пришли песню", "отправь песню", "скачай песню", "скинь песню", "аудио")
    if any(word in message.text.lower() for word in audio_words) and search_results:
        downloaded = await download_audio(search_results[0]["url"])
        if downloaded:
            audio_file, audio_title = downloaded
            try:
                from aiogram.types import FSInputFile
                await message.answer_audio(FSInputFile(str(audio_file)), title=audio_title[:64], performer=search_results[0].get("channel", ""))
                audio_sent = True
            finally:
                remove_audio(audio_file)
    if should_search_web(message.text) and not youtube_requested:
        web_results = await search_web(message.text)
    if youtube_requested and not search_results:
        search_results = await search_youtube(youtube_query(message.text))
    events_result = await db_session.execute(select(ImportantEvent).where(ImportantEvent.user_id == user.id).order_by(ImportantEvent.occurred_at.desc()).limit(20))
    events = [{"title": event.title, "event_type": event.event_type, "importance": event.importance, "description": event.description} for event in events_result.scalars()]
    memory_for_reply = dict(user.memory or {})
    if events:
        memory_for_reply["important_events"] = events
    recalled = await recall(db_session, user.id, message.text)
    if recalled:
        memory_for_reply["related_previous_context"] = recalled
    reply = await generate_reply(recent_context(updated_messages), memory_for_reply, ([] if audio_sent else search_results) + web_results)
    if web_results:
        reply += "\n\n🌐 Источники:\n" + "\n".join(f"• {item['title']} — {item['url']}" for item in web_results[:5])
    if search_results and not audio_sent:
        reply += "\n\n🎵 Музыка и видео:\n" + "\n".join(f"• {item['title']} — {item['url']}" for item in search_results)
    marketplace_words = ("wildberries", "вб", "вайлдберриз", "ozon", "озон", "товар", "купить")
    if any(word in message.text.lower() for word in marketplace_words):
        reply += "\n\n🛒 Поиск товара:\n" + format_marketplace_links(message.text)
    await answer_reply(message, reply, user)
    append_session_message(session, "assistant", reply)
    await remember(db_session, user.id, f"Пользователь: {message.text}\nALTER: {reply}")

    try:
        await db_session.commit()
        await db_session.refresh(session)
        print(f"✅ DEBUG: Сессия {session.id} успешно сохранена в Postgres!")
    except Exception as e:
        print(f"❌ DEBUG ОШИБКА СОХРАНЕНИЯ: {e}")

