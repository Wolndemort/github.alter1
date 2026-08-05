from datetime import datetime, timedelta, timezone

from aiogram import F, Router, types
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command, CommandStart
from aiogram.filters.command import CommandObject
from sqlalchemy import delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from data.models import ImportantEvent, Reminder, User, Session, Payment
from utils.ap_logic import generate_reply, plan_audio_request
from utils.media_logic import extract_visual_context, generate_media_reply
from utils.media import video_audio, video_duration, video_preview
from io import BytesIO
from utils.youtube_search import search_youtube
from utils.audio_search import download_audio, remove_audio
from utils.weather import get_weather, is_weather_request, parse_weather_city
from utils.marketplace_links import format_marketplace_links
from utils.keyboards import memory_keyboard, memory_categories_keyboard, settings_keyboard, cabinet_keyboard, voice_keyboard, SETTINGS_BACK_BUTTON, SETTINGS_BUTTON, VOICE_BUTTON, VOICE_ON_BUTTON, VOICE_OFF_BUTTON, BUY_SUBSCRIPTION_BUTTON, CABINET_BUTTON, SUPPORT_BUTTON, BACK_BUTTON, AUTO_RENEW_ON_BUTTON, AUTO_RENEW_OFF_BUTTON, UNLINK_CARD_BUTTON
from utils.reminders import extract_reminder_text, is_reminder_request, parse_reminder, parse_time_answer
from utils.voice import transcribe_voice
from utils.tts import synthesize_speech
from utils.vector_memory import recall, remember
from utils.tasks import process_session
from utils.intent import explicit_memory_fact, is_youtube_request, youtube_query
from sqlalchemy.orm.attributes import flag_modified
from config import config
from utils.billing import check_and_activate, configured as billing_configured, create_payment, has_active_subscription, is_owner, price
import logging

router = Router()


def voice_enabled(user: User) -> bool:
    return (user.tech_stack or {}).get("voice_replies", config.VOICE_REPLY_DEFAULT)


async def answer_reply(message: types.Message, reply: str, user: User, force_voice: bool = False):
    """Send text and, when enabled, a voice copy. TTS failure never hides the text."""
    await message.answer(reply)
    if force_voice or voice_enabled(user):
        try:
            audio = await synthesize_speech(reply)
        except Exception:
            logging.exception("Optional voice reply failed")
            audio = None
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
    await message.answer("Выбери режим: /checkins_on или /checkins_off", reply_markup=settings_keyboard())


@router.message(F.text == BUY_SUBSCRIPTION_BUTTON)
async def button_buy_subscription(message: types.Message, db_session: AsyncSession):
    await cmd_buy(message, db_session)


@router.message(F.text == CABINET_BUTTON)
async def button_cabinet(message: types.Message, db_session: AsyncSession):
    user = await db_session.get(User, message.from_user.id)
    if is_owner(message.from_user.id):
        status = "Владелец ALTER — доступ открыт без подписки."
    elif has_active_subscription(user):
        expires = user.subscription_expires_at.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
        status = f"Подписка активна до {expires}."
    else:
        status = "Подписка не активна."
    name = (user.first_name if user else None) or message.from_user.first_name or "друг"
    await message.answer(
        f"👋 Привет, {name}!\n\n"
        f"👤 Это твой кабинет ALTER\n\n{status}\n\n"
        f"Стоимость доступа: {price()} ₽ / {config.SUBSCRIPTION_DAYS} дней\n\n"
        "ALTER рядом и не забудет напомнить о важных вещах.",
        reply_markup=cabinet_keyboard(bool(user and user.auto_renew), bool(user and user.payment_method_id)),
    )


@router.message(F.text.in_({AUTO_RENEW_ON_BUTTON, AUTO_RENEW_OFF_BUTTON}))
async def button_auto_renew(message: types.Message, db_session: AsyncSession):
    user = await db_session.get(User, message.from_user.id)
    if not user or not user.payment_method_id:
        await message.answer("Сначала нужна одна обычная оплата — после неё можно включить автопродление.", reply_markup=cabinet_keyboard())
        return
    user.auto_renew = message.text == AUTO_RENEW_ON_BUTTON
    user.next_charge_at = user.subscription_expires_at if user.auto_renew else None
    await db_session.commit()
    state = "включено" if user.auto_renew else "выключено"
    await message.answer(f"Автопродление {state}.", reply_markup=cabinet_keyboard(user.auto_renew, bool(user.payment_method_id)))


@router.message(F.text == UNLINK_CARD_BUTTON)
async def button_unlink_card(message: types.Message, db_session: AsyncSession):
    user = await db_session.get(User, message.from_user.id)
    if user:
        user.payment_method_id = None
        user.auto_renew = False
        user.next_charge_at = None
        await db_session.commit()
    await message.answer("Карта отвязана от автопродления ALTER. Следующая оплата потребует новую привязку.", reply_markup=cabinet_keyboard())


@router.message(F.text == SUPPORT_BUTTON)
async def button_support(message: types.Message):
    await message.answer(
        "Если что-то не работает или есть предложение — напиши в поддержку.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Написать Адаму", url=f"tg://user?id={config.SUPPORT_TELEGRAM_ID}")],
        ]),
    )


@router.message(F.text == BACK_BUTTON)
async def button_cabinet_back(message: types.Message):
    await message.answer("Главное меню", reply_markup=memory_keyboard())


@router.message(F.text == SETTINGS_BUTTON)
async def button_settings(message: types.Message, db_session: AsyncSession):
    await cmd_settings(message, db_session)


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


@router.message(F.text == SETTINGS_BACK_BUTTON)
async def button_settings_back(message: types.Message):
    await message.answer("Главное меню", reply_markup=memory_keyboard())


@router.message(F.text.in_({"identity", "goals_habits", "skills_career", "interests_hobbies", "open_loops"}))
async def button_forget_category(message: types.Message, command: CommandObject, db_session: AsyncSession):
    await cmd_forget(message, CommandObject(args=message.text), db_session)


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "<b>ALTER умеет:</b>\n\n"
        "🧠 Память — факты о тебе, цели, интересы и незавершённые темы\n"
        "💬 Диалог — объяснения, идеи, планы, тексты и помощь с решениями\n"
        "🎙️ Голос — расшифровка голосовых и голосовые ответы\n"
        "🖼️ Медиа — анализ фотографий и коротких видео\n"
        "🎵 YouTube — поиск музыки и видео, отправка найденного аудио\n"
        "🌐 Поиск — актуальные факты, люди, товары, рекомендации и новости\n"
        "🌤️ Погода — прогноз по городу\n"
        "⏰ Напоминания — задачи, follow-up и мягкие check-in\n\n"
        "<b>Полезные команды:</b>\n"
        "/memory — что ALTER помнит\n"
        "/forget — забыть категорию\n"
        "/clear_memory — очистить память\n"
        "/new_session — начать новый разговор\n"
        "/remind — создать напоминание\n"
        "/settings — настройки\n"
        "/status — статус подписки\n"
        "/buy — продлить доступ",
        parse_mode="HTML",
    )
    return
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


def _settings_text(user: User) -> str:
    settings = user.tech_stack or {}
    return (
        "⚙️ Настройки ALTER:\n"
        f"• check-in: раз в {settings.get('checkin_interval_hours', 24)} ч.\n"
        f"• проверка самочувствия: через {settings.get('health_followup_hours', 4)} ч.\n"
        f"• тихие часы: {settings.get('quiet_start', 23):02d}:00–{settings.get('quiet_end', 8):02d}:00\n\n"
        "Команды:\n"
        "/checkin_every 24 — частота check-in в часах\n"
        "/health_followup 4 — задержка проверки самочувствия\n"
        "/quiet_hours 23 8 — тихие часы"
    )


@router.message(Command("settings"))
async def cmd_settings(message: types.Message, db_session: AsyncSession):
    user = await get_or_create_user(message, db_session)
    await message.answer(_settings_text(user), reply_markup=settings_keyboard())


async def _set_numeric_setting(message: types.Message, db_session: AsyncSession, key: str, label: str, low: int, high: int):
    parts = (message.text or "").split()
    try:
        value = int(parts[1])
    except (IndexError, ValueError):
        await message.answer(f"Формат: {parts[0]} число")
        return
    if not low <= value <= high:
        await message.answer(f"Укажи число от {low} до {high}.")
        return
    user = await get_or_create_user(message, db_session)
    settings = dict(user.tech_stack or {})
    settings[key] = value
    user.tech_stack = settings
    await db_session.commit()
    await message.answer(f"Готово: {label} — {value} ч.")


@router.message(Command("checkin_every"))
async def cmd_checkin_every(message: types.Message, db_session: AsyncSession):
    await _set_numeric_setting(message, db_session, "checkin_interval_hours", "check-in каждые", 1, 168)


@router.message(Command("health_followup"))
async def cmd_health_followup(message: types.Message, db_session: AsyncSession):
    await _set_numeric_setting(message, db_session, "health_followup_hours", "проверка самочувствия через", 1, 48)


@router.message(Command("quiet_hours"))
async def cmd_quiet_hours(message: types.Message, db_session: AsyncSession):
    parts = (message.text or "").split()
    try:
        start, end = int(parts[1]), int(parts[2])
    except (IndexError, ValueError):
        await message.answer("Формат: /quiet_hours 23 8")
        return
    if not 0 <= start <= 23 or not 0 <= end <= 23:
        await message.answer("Часы должны быть от 0 до 23.")
        return
    user = await get_or_create_user(message, db_session)
    settings = dict(user.tech_stack or {})
    settings.update({"quiet_start": start, "quiet_end": end})
    user.tech_stack = settings
    await db_session.commit()
    await message.answer(f"Тихие часы установлены: {start:02d}:00–{end:02d}:00.")


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
        audio_plan = await plan_audio_request(text)
        if audio_plan.get("download_audio"):
            results = await search_youtube(audio_plan.get("query") or text)
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
        user = await get_or_create_user(message, db_session)
        session = await get_active_session(user.id, db_session)
        if session is None:
            session = Session(user_id=user.id, raw_messages=[])
            db_session.add(session)
            await db_session.flush()
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
        # Media analysis also uses the semantic tool loop; no phrase matching.
        web_results = []
        kind = "Фото" if message.photo else "Видео"
        reply = await generate_media_reply(
            prompt,
            media,
            # The current media turn is supplied separately with the image/
            # video; keep only previous turns in the conversational history.
            conversation_context=recent_context(session.raw_messages[:-1]),
            memory=dict(user.memory or {}),
            search_results=web_results,
        )
        if web_results:
            reply += "\n\n🌐 Источники:\n" + "\n".join(
                f"• {item['title']} — {item['url']}" for item in web_results[:5]
            )
        await message.answer(reply)
        visual_context = await extract_visual_context(prompt, media)
        media_ref = {
            "media_type": "image/jpeg" if message.photo else "video/mp4",
            "file_id": message.photo[-1].file_id if message.photo else message.video.file_id,
        }
        context_suffix = f"\nВизуальный контекст: {visual_context}" if visual_context else ""
        append_session_message(session, "user", f"[{kind}] {prompt}{context_suffix}", media=media_ref)
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


def append_session_message(session: Session, role: str, content: str, media: dict | None = None) -> None:
    """Append a user or assistant turn to the short-term transcript."""
    messages = list(session.raw_messages or [])
    item = {"role": role, "content": content, "timestamp": datetime.utcnow().isoformat()}
    if media:
        item["media"] = media
    messages.append(item)
    session.raw_messages = messages


async def restore_session_media(bot, media_ref: dict) -> list[tuple[str, bytes]]:
    """Restore the latest Telegram media turn for a visual follow-up."""
    file_id = media_ref.get("file_id")
    media_type = media_ref.get("media_type")
    if not file_id or not media_type:
        return []
    try:
        buffer = await bot.download(file_id, destination=BytesIO())
        data = buffer.getvalue()
        if media_type.startswith("image/"):
            return [(media_type, data)]
        if media_type.startswith("video/"):
            return await video_preview(data)
    except Exception:
        logging.exception("Failed to restore media context")
    return []


def recent_context(messages: list, limit: int = 40, max_chars: int = 12000) -> list:
    """Keep the newest turns while bounding prompt size and preserving order."""
    selected = []
    chars = 0
    for item in reversed(list(messages or [])[-limit:]):
        content = str(item.get("content", "")) if isinstance(item, dict) else str(item)
        if selected and chars + len(content) > max_chars:
            break
        selected.append(item)
        chars += len(content)
    return list(reversed(selected))


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


@router.message(Command("buy"))
async def cmd_buy(message: types.Message, db_session: AsyncSession):
    if is_owner(message.from_user.id):
        await message.answer("Для владельца ALTER подписка не нужна.")
        return
    if has_active_subscription(await db_session.get(User, message.from_user.id)):
        await message.answer("У тебя уже есть активная подписка. Проверить срок можно через /status.")
        return
    if not billing_configured():
        await message.answer("Оплата пока настраивается. Попробуй немного позже.")
        return
    try:
        me = await message.bot.get_me()
        user = await get_or_create_user(message, db_session)
        card_url = await create_payment(db_session, user, me.username or "", "bank_card")
        sbp_url = await create_payment(db_session, user, me.username or "", "sbp")
        await message.answer(
            f"Подписка ALTER на {config.SUBSCRIPTION_DAYS} дней — {price()} ₽.\n\nНажми кнопку для оплаты:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 Оплатить картой", url=card_url)],
                [InlineKeyboardButton(text="💠 Оплатить через СБП", url=sbp_url)],
            ]),
        )
    except Exception:
        logging.exception("Failed to create YooKassa payment")
        await message.answer("Не удалось создать оплату. Попробуй ещё раз позже.")


@router.message(Command("status"))
async def cmd_status(message: types.Message, db_session: AsyncSession):
    user = await db_session.get(User, message.from_user.id)
    if is_owner(message.from_user.id):
        await message.answer("Ты владелец ALTER — доступ без подписки.")
    elif user and not has_active_subscription(user):
        pending_payments = (await db_session.execute(
            select(Payment).where(Payment.user_id == user.id, Payment.status == "pending")
            .order_by(Payment.created_at.desc())
        )).scalars().all()
        for pending in pending_payments:
            try:
                if await check_and_activate(db_session, pending.idempotence_key):
                    break
            except Exception:
                logging.exception("Failed to refresh pending YooKassa payment")
        if has_active_subscription(user):
            expires = user.subscription_expires_at.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
            await message.answer(f"Оплата подтверждена, подписка активна до {expires}.")
        else:
            await message.answer("Платёж ещё не подтверждён. Если уже оплатил, подожди минуту и повтори /status.")
    elif has_active_subscription(user):
        expires = user.subscription_expires_at.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
        await message.answer(f"Подписка активна до {expires}.")
    else:
        await message.answer("Активной подписки нет. Используй /buy, чтобы получить доступ на 30 дней.")


def legal_keyboard() -> InlineKeyboardMarkup:
    base = config.LEGAL_BASE_URL.rstrip("/")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 Политика конфиденциальности", url=f"{base}/privacy")],
        [InlineKeyboardButton(text="🛡 Согласие на обработку данных", url=f"{base}/consent")],
        [InlineKeyboardButton(text="📜 Публичная оферта", url=f"{base}/offer")],
        [InlineKeyboardButton(text="💳 Оплата и возврат", url=f"{base}/refund")],
        [InlineKeyboardButton(text="✅ Принять и продолжить", callback_data="accept_legal")],
    ])


def legal_consent_text(name: str) -> str:
    return (
        f"👋 Привет, {name}!\n\n"
        "Перед началом работы с ALTER ознакомься с политикой конфиденциальности и публичной офертой.\n\n"
        "Нажимая «Принять и продолжить», ты подтверждаешь, что ознакомился с документами, "
        "согласен на обработку персональных данных для работы сервиса и принимаешь условия оферты.\n\n"
        "ALTER обрабатывает Telegram-профиль, сообщения, память, голос и медиа только для выполнения функций, "
        "которые ты используешь."
    )


@router.callback_query(F.data == "accept_legal")
async def accept_legal(callback: types.CallbackQuery, db_session: AsyncSession):
    user = await db_session.get(User, callback.from_user.id)
    if user is None:
        user = User(
            id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name or "Пользователь",
            memory={}, tech_stack={},
        )
        db_session.add(user)
    user.legal_accepted_at = datetime.now(timezone.utc)
    await db_session.commit()
    await callback.answer("Условия приняты")
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(
        f"✅ Спасибо, {user.first_name or 'друг'}! Добро пожаловать в ALTER.",
        reply_markup=memory_keyboard(),
    )


@router.message(CommandStart())
async def cmd_start_welcome(message: types.Message, db_session: AsyncSession, command: CommandObject | None = None):
    user = await get_or_create_user(message, db_session)
    start_arg = (command.args or "").strip() if command else ""
    if start_arg.startswith("payment_"):
        try:
            activated = await check_and_activate(db_session, start_arg.removeprefix("payment_"))
        except Exception:
            logging.exception("Failed to check YooKassa payment")
            activated = False
        if activated:
            await message.answer(f"Оплата получена. Доступ ALTER открыт на {config.SUBSCRIPTION_DAYS} дней.\nПроверить срок: /status")
        else:
            await message.answer("Платёж ещё обрабатывается. Через минуту нажми /status или снова открой ссылку из оплаты.")
        return
    if user.legal_accepted_at is None:
        await db_session.commit()
        await message.answer(
            legal_consent_text(user.first_name or message.from_user.first_name or "друг"),
            reply_markup=legal_keyboard(),
        )
        return
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
    text = (
        f"✨ <b>Привет, {name}!</b>\n\n"
        "Я — <b>ALTER</b>, твой персональный AI-ассистент, который помнит контекст и развивается вместе с тобой.\n\n"
        "<b>Что я умею:</b>\n"
        "🧠 запоминать важные факты, цели, привычки и незавершённые темы\n"
        "💬 поддерживать живой диалог и помогать разбираться в задачах\n"
        "🎙️ расшифровывать голосовые и отвечать голосом\n"
        "🖼️ анализировать фотографии и короткие видео\n"
        "🎵 находить музыку и видео на YouTube и отправлять аудио\n"
        "🌐 искать актуальную информацию, товары, людей и рекомендации\n"
        "🌤️ смотреть погоду и объяснять сложное простым языком\n"
        "⏰ ставить напоминания, возвращаться к важным темам и делать мягкие check-in\n\n"
        "Просто напиши, что тебе нужно. Память, настройки и подписка — в кнопках ниже.\n\n"
        "<i>ALTER рядом, чтобы разговоры и важные вещи не терялись.</i>"
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
        await message.answer(f"Я жду время для напоминания про «{pending['text']}». Например: 18:30 или через 2 часа.")
        return

    parsed_reminder = parse_reminder(message.text)
    if parsed_reminder:
        remind_at, reminder_text = parsed_reminder
        db_session.add(Reminder(user_id=user.id, remind_at=remind_at, follow_up_at=remind_at + timedelta(hours=2), text=reminder_text[:500]))
        await db_session.commit()
        await message.answer(f"Записал. Напомню {remind_at.strftime('%d.%m в %H:%M')}: {reminder_text}")
        return

    if is_reminder_request(message.text):
        reminder_text = extract_reminder_text(message.text)
        if not reminder_text:
            await message.answer("Что именно напомнить и во сколько?")
            return
        user.pending_reminder = {"text": reminder_text[:500]}
        await db_session.commit()
        await message.answer(f"Хорошо. Во сколько напомнить про «{reminder_text}»?")
        return

    plan_words = ("завтра иду", "завтра пойду", "завтра буду", "сегодня иду", "сегодня пойду", "сегодня буду")
    if any(phrase in message.text.lower() for phrase in plan_words):
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
    # Weather is handled deterministically so a provider/model tool decision
    # cannot turn a simple forecast request into a vague AI refusal.
    events_result = await db_session.execute(select(ImportantEvent).where(ImportantEvent.user_id == user.id).order_by(ImportantEvent.occurred_at.desc()).limit(20))
    events = [{"title": event.title, "event_type": event.event_type, "importance": event.importance, "description": event.description} for event in events_result.scalars()]
    memory_for_reply = dict(user.memory or {})
    if events:
        memory_for_reply["important_events"] = events
    recalled = await recall(db_session, user.id, message.text)
    if recalled:
        memory_for_reply["related_previous_context"] = recalled
    previous_media = next(
        (
            item.get("media")
            for item in reversed(updated_messages[:-1])
            if item.get("role") == "user" and item.get("media")
        ),
        None,
    )
    restored_media = await restore_session_media(message.bot, previous_media) if previous_media else []
    if restored_media:
        reply = await generate_media_reply(
            message.text,
            restored_media,
            conversation_context=recent_context(updated_messages[:-1]),
            memory=memory_for_reply,
                search_results=[],
        )
    elif is_weather_request(message.text):
        city = parse_weather_city(message.text)
        reply = await get_weather(city) or f"Не удалось получить актуальный прогноз для {city}. Попробуй ещё раз через минуту."
    else:
        reply = await generate_reply(recent_context(updated_messages), memory_for_reply)
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

