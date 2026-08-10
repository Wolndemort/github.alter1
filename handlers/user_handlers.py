from datetime import datetime, timedelta, timezone

from aiogram import F, Router, types
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command, CommandStart
from aiogram.filters.command import CommandObject
from sqlalchemy import delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from data.models import ImportantEvent, Reminder, User, Session, Payment, MemoryChunk
from data.database import async_session
from utils.ap_logic import generate_reply, plan_audio_request
from utils.media_logic import extract_visual_context, generate_media_reply
from services.media_generation import generate_image, generate_video
from utils.media import video_audio, video_duration, video_preview
from io import BytesIO
from utils.youtube_search import search_youtube
from utils.audio_search import download_audio, remove_audio
from utils.weather import get_weather, is_weather_request, parse_weather_city
from utils.marketplace_links import format_marketplace_links
from utils.keyboards import memory_keyboard, memory_categories_keyboard, settings_keyboard, cabinet_keyboard, voice_keyboard, media_actions_keyboard, SETTINGS_BACK_BUTTON, SETTINGS_BUTTON, VOICE_BUTTON, VOICE_ON_BUTTON, VOICE_OFF_BUTTON, BUY_SUBSCRIPTION_BUTTON, CABINET_BUTTON, SUPPORT_BUTTON, BACK_BUTTON, AUTO_RENEW_ON_BUTTON, AUTO_RENEW_OFF_BUTTON, UNLINK_CARD_BUTTON
from utils.reminders import extract_reminder_text, is_reminder_request, parse_reminder, parse_time_answer
from utils.voice import transcribe_voice
from utils.audio_actions import detect_audio_action, process_audio_action
from utils.tts import synthesize_speech
from utils.vector_memory import recall, remember
from utils.tasks import process_session
from utils.intent import explicit_memory_fact, is_youtube_request, youtube_query, should_recall_context
from utils.capabilities import capabilities_reply, is_capabilities_request
from utils.calendar_intent import handle_calendar_request
from utils.generation_intent import generation_kind
from utils.memory_facts import extract_user_facts
from utils.feedback_memory import feedback_context
from utils.memory_store import merge_memory_facts
from utils.media_options import parse_media_options
from sqlalchemy.orm.attributes import flag_modified
from config import config
from utils.billing import check_and_activate, configured as billing_configured, create_payment, has_active_subscription, is_owner, price, plan_info, credits_limit, normalize_plan
from services.account_linking import link_telegram_identity, resolve_telegram_user
from services import google_calendar
from services.elevenlabs_media import ElevenLabsError, design_voice, list_voices
from services.voice_commands import is_voice_generation_request, voice_description
from utils.redis_store import consume_link_token, create_redis, close_redis, credits_used
from utils.quota import charge_user_id_credits
from utils.keyboards import STATUS_BUTTON, USAGE_BUTTON
from utils.keyboards import generated_image_keyboard
from utils.keyboards import VOICE_CREATE_BUTTON, VOICE_LIST_BUTTON
from utils.metrics import increment
import logging

router = Router()


def voice_enabled(user: User) -> bool:
    return (user.tech_stack or {}).get("voice_replies", config.VOICE_REPLY_DEFAULT)


async def generation_allowed(user: User, cost: int) -> bool:
    redis = create_redis()
    try:
        return await charge_user_id_credits(redis, user.id, cost, async_session)
    finally:
        await close_redis(redis)


async def answer_reply(message: types.Message, reply: str, user: User, force_voice: bool = False):
    """Send text and, when enabled, a voice copy. TTS failure never hides the text."""
    feedback_markup = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="👍 Полезно", callback_data="reply_feedback:positive"),
        InlineKeyboardButton(text="👎 Мимо", callback_data="reply_feedback:negative"),
    ]])
    try:
        await message.answer(reply, reply_markup=feedback_markup)
    except TypeError:
        # Keeps lightweight/offline Message doubles and older adapters working.
        await message.answer(reply)
    if force_voice or voice_enabled(user):
        try:
            selected_voice = (user.tech_stack or {}).get("tts_voice")
            audio = await synthesize_speech(reply, voice=selected_voice)
        except Exception:
            logging.exception("Optional voice reply failed")
            audio = None
        if audio:
            await message.answer_voice(BufferedInputFile(audio, filename="alter.ogg"))


@router.callback_query(F.data.startswith("reply_feedback:"))
async def handle_reply_feedback(callback: types.CallbackQuery, db_session: AsyncSession):
    rating = callback.data.rsplit(":", 1)[-1]
    if rating not in {"positive", "negative"} or not callback.from_user:
        await callback.answer()
        return
    user = await get_telegram_user(callback.from_user.id, db_session)
    if user:
        settings = dict(user.tech_stack or {})
        feedback = list(settings.get("reply_feedback") or [])
        answer = str(getattr(getattr(callback, "message", None), "text", "") or "").strip()
        feedback.append({"rating": rating, "answer": answer[:700], "at": datetime.now(timezone.utc).isoformat()})
        settings["reply_feedback"] = feedback[-100:]
        user.tech_stack = settings
        await db_session.commit()
    increment("ai.reply.feedback", rating=rating)
    await callback.answer("Спасибо, учту." if rating == "positive" else "Понял, буду точнее.")


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
    audio = await synthesize_speech(text, voice=(user.tech_stack or {}).get("tts_voice"))
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
    user = await get_telegram_user(message.from_user.id, db_session)
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
    user = await get_telegram_user(message.from_user.id, db_session)
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
    user = await get_telegram_user(message.from_user.id, db_session)
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


@router.message(F.text == STATUS_BUTTON)
async def button_status(message: types.Message, db_session: AsyncSession):
    await cmd_status(message, db_session)


@router.message(F.text == USAGE_BUTTON)
async def button_usage(message: types.Message, db_session: AsyncSession):
    user = await get_telegram_user(message.from_user.id, db_session)
    if not user:
        await message.answer("Сначала открой /start.", reply_markup=memory_keyboard())
        return
    redis = create_redis()
    try:
        used = await credits_used(redis, user.id)
    finally:
        await close_redis(redis)
    plan = normalize_plan((user.tech_stack or {}).get("subscription_plan"))
    limit = credits_limit(user)
    await message.answer(
        f"Тариф: {plan_info(plan)['name']}\n"
        f"Использовано: {used} из {limit} кредитов\n"
        f"Осталось: {max(0, limit - used)}",
        reply_markup=memory_keyboard(),
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


@router.message(F.text == VOICE_CREATE_BUTTON)
async def button_voice_create(message: types.Message):
    await message.answer("Напиши или скажи описание голоса. Например: «Создай спокойный низкий голос для подкаста»." )


@router.message(F.text == VOICE_LIST_BUTTON)
async def button_voice_list(message: types.Message):
    try:
        payload = await list_voices()
        voices = payload.get("voices", []) if isinstance(payload, dict) else []
        names = [str(item.get("name") or item.get("voice_id")) for item in voices[:20]]
        await message.answer("Доступные голоса:\n" + ("\n".join(f"• {name}" for name in names) if names else "Список пуст."))
    except ElevenLabsError:
        await message.answer("Не удалось загрузить голоса ElevenLabs.")


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
    faq_markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Открыть полный FAQ", url="https://api.alterai.ru/api/v1/faq")]])
    await message.answer(capabilities_reply(), reply_markup=faq_markup)
    return


@router.message(Command("faq"))
async def cmd_faq(message: types.Message):
    await message.answer("Полный FAQ ALTER: https://api.alterai.ru/api/v1/faq")
    return
    await message.answer("Полный FAQ ALTER: https://api.alterai.ru/api/v1/faq")
    await message.answer(
        "<b>ALTER</b> — просто напиши, что нужно.\n\n"
        "🧠 Память: «запомни, что…» или «забудь, что…»\n"
        "⏰ Напоминание: «напомни мне завтра в 10:00 позвонить…»\n"
        "💭 Check-in: ALTER сама иногда возвращается к важной теме\n"
        "🎙 Голос: отправь голосовое или попроси озвучить ответ\n"
        "🔊 Аудио: напиши «создай звук дождя», «почисти моё голосовое» или отправь голосовое с подписью «наложи звук дождя»\n"
        "📎 Фото и видео: отправь файл и напиши, что сделать\n\n"
        "Память, напоминания, настройки, подписка и лимиты — в кнопках меню.",
        parse_mode="HTML",
    )
    return

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
        audio_data = buffer.getvalue()
        caption = (message.caption or "").strip()
        text = caption or await transcribe_voice(audio_data)
        if not text:
            await message.answer("Не смог разобрать голосовое сообщение.")
            return
        user = await get_or_create_user(message, db_session)
        session = await get_active_session(user.id, db_session)
        if session is None:
            session = Session(user_id=user.id, raw_messages=[])
            db_session.add(session)
            await db_session.flush()
        if is_capabilities_request(text):
            reply = capabilities_reply()
            await answer_reply(message, reply, user)
            append_session_message(session, "user", text)
            append_session_message(session, "assistant", reply)
            await db_session.commit()
            return
        calendar_reply = await handle_calendar_request(text, user)
        if calendar_reply is not None:
            await answer_reply(message, calendar_reply, user)
            append_session_message(session, "user", text)
            append_session_message(session, "assistant", calendar_reply)
            await db_session.commit()
            return
        # Keep voice and text routing identical for deterministic integrations.
        # A forecast request should not depend on the model deciding to call
        # the weather tool after transcription.
        if is_weather_request(text):
            city = parse_weather_city(text)
            reply = await get_weather(city) or f"Не удалось получить актуальный прогноз для {city}. Попробуй ещё раз через минуту."
            await answer_reply(message, reply, user)
            append_session_message(session, "user", text)
            append_session_message(session, "assistant", reply)
            await db_session.commit()
            return
        if is_voice_generation_request(text):
            description = voice_description(text)
            if not description:
                await message.answer("Опиши голос подробнее и отправь команду ещё раз.")
                return
            try:
                generated = await design_voice(description)
                voice_id = str(generated.get("voice_id") or generated.get("id") or "").strip()
                if voice_id:
                    settings = dict(user.tech_stack or {})
                    settings["generated_voice_id"] = voice_id
                    user.tech_stack = settings
                    await db_session.commit()
                    await message.answer("Голос создан и сохранён. Теперь отправь голосовое с командой «измени мой голос на созданный».")
                else:
                    await message.answer("ElevenLabs не вернул идентификатор созданного голоса.")
            except ElevenLabsError:
                logging.exception("Voice generation from voice command failed")
                await message.answer("Не удалось создать голос сейчас. Проверь доступ ElevenLabs.")
            return
        requested_generation = generation_kind(text)
        if requested_generation == "image":
            if not await generation_allowed(user, config.FAL_TEXT_IMAGE_CREDITS):
                await message.answer("Лимит кредитов для генерации изображения исчерпан.")
                return
            artifact = await generate_image(text, options=parse_media_options(text, "image"))
            await message.answer_photo(BufferedInputFile(artifact.data, filename=artifact.filename), caption="Готово — создал изображение.", reply_markup=generated_image_keyboard())
            append_session_message(session, "user", text)
            append_session_message(session, "assistant", "Создал изображение.")
            await db_session.commit()
            return
        if requested_generation == "video":
            if not await generation_allowed(user, config.FAL_TEXT_VIDEO_CREDITS):
                await message.answer("Лимит кредитов для генерации видео исчерпан.")
                return
            artifact = await generate_video(text, options=parse_media_options(text, "video"))
            await message.answer_document(BufferedInputFile(artifact.data, filename=artifact.filename), caption="Готово — создал видео.")
            append_session_message(session, "user", text)
            append_session_message(session, "assistant", "Создал видео.")
            await db_session.commit()
            return
        action_source = audio_data
        action_filename = "voice.ogg"
        detected_action = detect_audio_action(text)
        # A spoken command can refer to the previous voice message. Keep the
        # command recording out of the mix and restore the prior Telegram file.
        if detected_action in {"mix", "isolate"} and not caption:
            previous = next((item.get("media") for item in reversed(session.raw_messages or []) if item.get("media", {}).get("media_type") == "audio/ogg"), None)
            if previous and previous.get("file_id"):
                previous_buffer = await message.bot.download(previous["file_id"], destination=BytesIO())
                action_source = previous_buffer.getvalue()
                action_filename = "previous.ogg"
        if detected_action and not await generation_allowed(user, 20):
            await message.answer("Лимит кредитов для аудио исчерпан.")
            return
        action_result = await process_audio_action(text, action_source, action_filename) if detected_action else None
        if action_result:
            answer, output = action_result
            await message.answer_audio(BufferedInputFile(output, filename="alter-audio.mp3"), caption=answer)
            append_session_message(session, "user", text)
            append_session_message(session, "assistant", answer)
            await db_session.commit()
            return
        if not await generation_allowed(user, 1):
            await message.answer("Лимит кредитов исчерпан.")
            return
        append_session_message(session, "user", text, media={"media_type": "audio/ogg", "file_id": message.voice.file_id})
        # Расшифровка используется только внутри ALTER и не отправляется пользователю.
        await message.bot.send_chat_action(message.chat.id, "typing")
        audio_plan = await plan_audio_request(text)
        if audio_plan.get("download_audio"):
            results = await search_youtube(audio_plan.get("query") or text)
            if results:
                downloaded = await download_audio(results[0]["url"])
                if downloaded:
                    if not await generation_allowed(user, config.YOUTUBE_AUDIO_CREDITS):
                        await message.answer("Лимит кредитов YouTube-аудио исчерпан.")
                        return
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


def media_generation_requested(prompt: str) -> bool:
    """Recognise a natural edit/generation command attached to media.

    Telegram captions are not required to use a command prefix.  Matching the
    first meaningful word keeps ordinary questions such as "что на фото?" on
    the vision-analysis path while accepting normal Russian instructions.
    """
    normalized = " ".join((prompt or "").casefold().strip().split())
    if not normalized:
        return False
    command_words = (
        "/edit",
        "измени", "изменить", "изменяй",
        "редактируй", "редактировать",
        "сделай", "создай", "нарисуй", "оживи",
        "добавь", "добавить", "убери", "убрать",
        "замени", "заменить", "надень", "переодень",
        "перекрась", "перекрасить",
    )
    first_word = normalized.split(" ", 1)[0].rstrip(" ,.!?:;—–-\n")
    return first_word in command_words


@router.message(lambda message: message.photo or message.video)
async def handle_media(message: types.Message, db_session: AsyncSession):
    prompt = message.caption or "Проанализируй это изображение и объясни, что на нём."
    try:
        user = await get_or_create_user(message, db_session)
        # A caption on attached media is a natural-language command.  Do not
        # require the API-style /edit prefix: users commonly write
        # "Редактируй фото, надень шляпу", "добавь фон" or "убери человека".
        generation_requested = media_generation_requested(prompt)
        if generation_requested:
            requested_kind = generation_kind(prompt)
            generation_cost = (
                config.FAL_TEXT_VIDEO_CREDITS
                if requested_kind == "video"
                else config.MEDIA_GENERATION_CREDITS
            )
            if not await generation_allowed(user, generation_cost):
                await message.answer("Лимит кредитов для генерации медиа исчерпан.")
                return
            if message.photo:
                buffer = await message.bot.download(message.photo[-1], destination=BytesIO())
                source = ("image/jpeg", buffer.getvalue())
                if requested_kind == "video":
                    artifact = await generate_video(prompt, source, parse_media_options(prompt, "video"))
                    await message.answer_document(BufferedInputFile(artifact.data, filename=artifact.filename))
                else:
                    artifact = await generate_image(prompt, source, parse_media_options(prompt, "image"))
                    await message.answer_photo(BufferedInputFile(artifact.data, filename=artifact.filename), reply_markup=generated_image_keyboard())
            else:
                buffer = await message.bot.download(message.video, destination=BytesIO())
                artifact = await generate_video(prompt, ("video/mp4", buffer.getvalue()), parse_media_options(prompt, "video"))
                # Video providers return an async job in the next adapter step.
                # Never claim a completed video while no artifact exists.
                if artifact:
                    await message.answer_document(BufferedInputFile(artifact.data, filename=artifact.filename))
            return
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
        if not await generation_allowed(user, 20):
            await message.answer("Лимит кредитов для анализа медиа исчерпан.")
            return
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
            memory={**dict(user.memory or {}), **({"response_feedback": feedback_context(user.tech_stack)} if feedback_context(user.tech_stack) else {})},
            search_results=web_results,
        )
        if web_results:
            reply += "\n\n🌐 Источники:\n" + "\n".join(
                f"• {item['title']} — {item['url']}" for item in web_results[:5]
            )
        await message.answer(reply, reply_markup=media_actions_keyboard())
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
        logging.exception("Telegram media handler failed")
        await message.answer("Не удалось обработать этот файл.")


@router.callback_query(F.data == "media:improve")
async def improve_media_photo(callback: types.CallbackQuery, db_session: AsyncSession):
    message = callback.message
    user = await get_telegram_user(callback.from_user.id, db_session) if callback.from_user else None
    if user and not await generation_allowed(user, config.MEDIA_GENERATION_CREDITS):
        await callback.answer("Лимит кредитов для генерации медиа исчерпан.", show_alert=True)
        return
    session = await get_active_session(user.id, db_session) if user else None
    media_ref = next((item.get("media") for item in reversed(session.raw_messages if session else []) if item.get("role") == "user" and item.get("media")), None)
    restored = await restore_session_media(message.bot, media_ref) if message and media_ref else []
    if not restored or not restored[0][0].startswith("image/"):
        await callback.answer("Кнопка работает для фото", show_alert=True)
        return
    try:
        artifact = await generate_image("Сделай изображение более дорогим, кинематографичным и аккуратным, сохранив человека и ключевые детали.", restored[0])
        await message.answer_photo(BufferedInputFile(artifact.data, filename=artifact.filename), caption="Готово — сохранил исходный характер изображения.")
        await callback.answer()
    except Exception:
        await callback.answer("Генерация сейчас недоступна — проверь баланс или попробуй позже.", show_alert=True)


@router.callback_query(F.data == "media:analyze")
async def analyze_media_again(callback: types.CallbackQuery):
    await callback.answer("Анализ уже показан сообщением ALTER выше.")


@router.callback_query(F.data == "media:edit_generated")
async def edit_generated_image(callback: types.CallbackQuery, db_session: AsyncSession):
    """Re-edit the generated image without requiring the user to re-upload it."""
    message = callback.message
    user = await get_telegram_user(callback.from_user.id, db_session) if callback.from_user else None
    if user and not await generation_allowed(user, config.MEDIA_GENERATION_CREDITS):
        await callback.answer("Лимит кредитов для генерации медиа исчерпан.", show_alert=True)
        return
    if not message or not message.photo:
        await callback.answer("Исходное изображение недоступно.", show_alert=True)
        return
    try:
        buffer = await message.bot.download(message.photo[-1], destination=BytesIO())
        artifact = await generate_image(
            "Сделай изображение более аккуратным и кинематографичным, сохранив основной сюжет и ключевые детали.",
            ("image/jpeg", buffer.getvalue()),
        )
        await message.answer_photo(
            BufferedInputFile(artifact.data, filename=artifact.filename),
            caption="Готово — отредактировал изображение.",
            reply_markup=generated_image_keyboard(),
        )
        await callback.answer()
    except Exception:
        logging.exception("Generated image edit failed")
        await callback.answer("Редактирование сейчас недоступно — проверь баланс Fal AI.", show_alert=True)


@router.callback_query(F.data == "media:animate")
async def animate_media_video(callback: types.CallbackQuery):
    await callback.answer("Оживление видео подключено; сейчас провайдер вернёт статус после запуска задачи.", show_alert=True)


def format_memory(memory: dict) -> str:
    from utils.memory_view import format_memory as render_memory
    return render_memory(memory)


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


def refers_to_previous_media(text: str) -> bool:
    """Return whether a text message explicitly asks about the last media turn."""
    value = (text or "").casefold().replace("ё", "е")
    markers = (
        "на фото", "по фото", "с фото", "на картинке", "по картинке",
        "на изображении", "по изображению", "на скрине", "по скрину",
        "что видно", "что изображено", "этот предмет", "этот товар",
        "какой цвет", "какой размер", "какая модель", "подойдет ли",
        "подойдет", "подойдет ли", "на нем", "на ней", "на нём",
    )
    return any(marker in value for marker in markers)


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
    user = await resolve_telegram_user(db_session, message.from_user.id)
    if user is None:
        user = User(id=message.from_user.id,
                    username=message.from_user.username,
                    first_name=message.from_user.first_name or "Пользователь",
                    memory={}, tech_stack={})
        db_session.add(user)
        await db_session.flush()
    return user


async def get_telegram_user(telegram_user_id: int, db_session: AsyncSession) -> User | None:
    return await resolve_telegram_user(db_session, telegram_user_id)


@router.message(Command("buy"))
async def cmd_buy(message: types.Message, db_session: AsyncSession):
    if is_owner(message.from_user.id):
        await message.answer("Для владельца ALTER подписка не нужна.")
        return
    if has_active_subscription(await get_telegram_user(message.from_user.id, db_session)):
        await message.answer("У тебя уже есть активная подписка. Проверить срок можно через /status.")
        return
    if not billing_configured():
        await message.answer("Оплата пока настраивается. Попробуй немного позже.")
        return
    try:
        me = await message.bot.get_me()
        user = await get_or_create_user(message, db_session)
        personal_card = await create_payment(db_session, user, me.username or "", "bank_card", "personal")
        personal_sbp = await create_payment(db_session, user, me.username or "", "sbp", "personal")
        ego_card = await create_payment(db_session, user, me.username or "", "bank_card", "ego")
        ego_sbp = await create_payment(db_session, user, me.username or "", "sbp", "ego")
        await message.answer(
            "Выбери тариф ALTER:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"ALTER Personal · {price('personal')} ₽ · карта", url=personal_card)],
                [InlineKeyboardButton(text="Personal · СБП", url=personal_sbp)],
                [InlineKeyboardButton(text=f"ALTER Ego · {price('ego')} ₽ · карта", url=ego_card)],
                [InlineKeyboardButton(text="Ego · СБП", url=ego_sbp)],
            ]),
        )
        return
    except Exception:
        logging.exception("Failed to create plan payments")
        await message.answer("Не удалось открыть тарифы. Попробуй ещё раз позже.")
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
    user = await get_telegram_user(message.from_user.id, db_session)
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
        [InlineKeyboardButton(text="📄 Политика конфиденциальности", url=f"{base}/legal/privacy.html")],
        [InlineKeyboardButton(text="🛡 Согласие на обработку данных", url=f"{base}/legal/consent.html")],
        [InlineKeyboardButton(text="📜 Публичная оферта", url=f"{base}/legal/offer.html")],
        [InlineKeyboardButton(text="💳 Оплата и возврат", url=f"{base}/legal/refund.html")],
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
    user = await get_telegram_user(callback.from_user.id, db_session)
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
async def cmd_start_welcome(message: types.Message, db_session: AsyncSession, command: CommandObject | None = None, redis=None):
    start_arg = (command.args or "").strip() if command else ""
    if start_arg.startswith("link_"):
        if redis is None:
            await message.answer("Связка временно недоступна. Попробуй ещё раз позже.")
            return
        app_user_id = await consume_link_token(redis, start_arg.removeprefix("link_"))
        if app_user_id is None:
            await message.answer("Ссылка устарела или уже использована. Создай новую ссылку в приложении.")
            return
        try:
            user = await link_telegram_identity(
                db_session, app_user_id, message.from_user.id,
                message.from_user.username, message.from_user.first_name,
            )
            user.legal_accepted_at = user.legal_accepted_at or datetime.now(timezone.utc)
            await db_session.commit()
        except ValueError as exc:
            await db_session.rollback()
            await message.answer(str(exc))
            return
        await message.answer("Telegram подключён. Теперь приложение и бот используют одну память и одну подписку.")
        return
    user = await get_or_create_user(message, db_session)
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
    await db_session.execute(delete(MemoryChunk).where(MemoryChunk.user_id == user.id))
    await db_session.commit()
    await message.answer("Долгосрочная память очищена.", reply_markup=memory_keyboard())


@router.message(Command("clear_context"))
async def cmd_clear_context(message: types.Message, db_session: AsyncSession):
    """Remove recalled conversation snippets without deleting user facts."""
    user = await get_or_create_user(message, db_session)
    await db_session.execute(delete(MemoryChunk).where(MemoryChunk.user_id == user.id))
    await db_session.commit()
    await message.answer("Контекст старых разговоров очищен. Факты о тебе сохранены.", reply_markup=memory_keyboard())


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
    user = await get_or_create_user(message, db_session)
    result = await db_session.execute(select(Reminder).where(
        Reminder.user_id == user.id,
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
    user = await get_or_create_user(message, db_session)
    try:
        reminder_id = int((command.args or "").strip())
    except ValueError:
        await message.answer("Формат: /cancel_reminder ID")
        return
    result = await db_session.execute(select(Reminder).where(
        Reminder.id == reminder_id, Reminder.user_id == user.id,
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


@router.message(Command("calendar_connect"))
async def cmd_calendar_connect(message: types.Message, db_session: AsyncSession):
    if not google_calendar.configured():
        await message.answer("Google Calendar пока не настроен на сервере.")
        return
    user = await get_or_create_user(message, db_session)
    try:
        await message.answer("Открой ссылку и разреши ALTER доступ к Google Calendar:\n\n" + google_calendar.authorization_url(user.id))
    except Exception:
        logging.exception("Calendar OAuth URL failed")
        await message.answer("Не удалось подготовить подключение Google Calendar.")


@router.message(Command("calendar"))
async def cmd_calendar(message: types.Message, db_session: AsyncSession):
    user = await get_or_create_user(message, db_session)
    try:
        events = await google_calendar.list_events(user)
    except Exception:
        await message.answer("Сначала подключи календарь командой /calendar_connect.")
        return
    if not events:
        await message.answer("На ближайшее время событий нет.")
        return
    lines = ["Ближайшие события:"]
    for item in events[:10]:
        start = item.get("start", {}).get("dateTime") or item.get("start", {}).get("date", "")
        lines.append(f"• {start} — {item.get('summary', 'Без названия')}")
    await message.answer("\n".join(lines))


@router.message(Command("calendar_add"))
async def cmd_calendar_add(message: types.Message, command: CommandObject, db_session: AsyncSession):
    parts = (command.args or "").split(maxsplit=4)
    if len(parts) < 5:
        await message.answer("Формат: /calendar_add 2026-08-20 10:00 2026-08-20 11:00 название")
        return
    user = await get_or_create_user(message, db_session)
    event = {"summary": parts[4], "start": {"dateTime": f"{parts[0]}T{parts[1]}:00+03:00"}, "end": {"dateTime": f"{parts[2]}T{parts[3]}:00+03:00"}}
    try:
        created = await google_calendar.create_event(user, event)
        await message.answer(f"Событие добавлено: {created.get('summary', parts[4])}")
    except Exception:
        await message.answer("Не удалось добавить событие. Проверь подключение через /calendar_connect.")


@router.message(lambda message: message.text and detect_audio_action(message.text) == "effect")
async def handle_sound_effect_text(message: types.Message, db_session: AsyncSession):
    """Create a sound from an ordinary natural-language chat message."""
    user = await get_or_create_user(message, db_session)
    redis = create_redis()
    try:
        if not await charge_user_id_credits(redis, user.id, 20, async_session):
            await message.answer("Месячный лимит аудио исчерпан.")
            return
    finally:
        await close_redis(redis)
    try:
        _, output = await process_audio_action(message.text, b"")
        await message.answer_audio(BufferedInputFile(output, filename="alter-sound.mp3"), caption="Готово — создал звуковой эффект.")
    except Exception:
        logging.exception("Sound effect text request failed")
        await message.answer("Не удалось создать звук сейчас. Проверь баланс ElevenLabs и попробуй ещё раз.")


@router.message()
async def handle_any_message(message: types.Message, db_session: AsyncSession, billing_allowed: bool = True, spam_allowed: bool = True):
    """
    Хендлер для сохранения всех входящих сообщений в raw_messages.
    """
    if not message.text or not message.from_user:
        return
    if not spam_allowed:
        await message.answer("Слишком много сообщений подряд. Подожди немного и попробуй ещё раз.")
        return
    if not billing_allowed:
        await message.answer("Дневной лимит запросов исчерпан. Попробуй завтра.")
        return

    user = await get_or_create_user(message, db_session)
    if is_capabilities_request(message.text):
        await message.answer(capabilities_reply())
        await db_session.commit()
        return
    if is_voice_generation_request(message.text):
        description = voice_description(message.text)
        if not description:
            await message.answer("Опиши голос: например, «создай спокойный низкий голос для подкаста».")
            return
        try:
            generated = await design_voice(description)
            voice_id = str(generated.get("voice_id") or generated.get("id") or "").strip()
            if voice_id:
                settings = dict(user.tech_stack or {})
                settings["generated_voice_id"] = voice_id
                user.tech_stack = settings
                await db_session.commit()
                await message.answer("Голос создан и сохранён. Прикрепи голосовое и напиши: «измени мой голос на созданный».")
            else:
                await message.answer("ElevenLabs создал голос, но не вернул его идентификатор.")
        except ElevenLabsError:
            logging.exception("Voice generation failed")
            await message.answer("Не удалось создать голос. Проверь доступ ElevenLabs и попробуй ещё раз.")
        return
    requested_generation = generation_kind(message.text)
    if requested_generation == "image":
        try:
            if not await generation_allowed(user, config.FAL_TEXT_IMAGE_CREDITS):
                await message.answer("Лимит кредитов для генерации изображения исчерпан.")
                return
            artifact = await generate_image(message.text, options=parse_media_options(message.text, "image"))
            await message.answer_photo(BufferedInputFile(artifact.data, filename=artifact.filename), caption="Готово — создал изображение.", reply_markup=generated_image_keyboard())
        except Exception:
            logging.exception("Text image generation failed")
            await message.answer("Не получилось создать изображение. Проверь Fal.ai и попробуй ещё раз.")
        return
    if requested_generation == "video":
        try:
            if not await generation_allowed(user, config.FAL_TEXT_VIDEO_CREDITS):
                await message.answer("Лимит кредитов для генерации видео исчерпан.")
                return
            artifact = await generate_video(message.text, options=parse_media_options(message.text, "video"))
            await message.answer_document(BufferedInputFile(artifact.data, filename=artifact.filename), caption="Готово — создал видео.")
        except Exception:
            logging.exception("Text video generation failed")
            await message.answer("Не получилось создать видео. Проверь Fal.ai и попробуй ещё раз.")
        return
    extracted_facts = extract_user_facts(message.text)
    if extracted_facts:
        user.memory = merge_memory_facts(dict(user.memory or {}), extracted_facts)
        flag_modified(user, "memory")
    explicit_fact = explicit_memory_fact(message.text)
    if explicit_fact:
        user.memory = merge_memory_facts(
            dict(user.memory or {}),
            {"preferences": {"explicit_facts": [explicit_fact]}},
        )
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
        Session.user_id == user.id,
        Session.is_processed.is_(False),
    ).order_by(Session.started_at.desc())

    result = await db_session.execute(stmt)
    session = result.scalar_one_or_none()

    if not session:
        session = Session(user_id=user.id, raw_messages=[])
        db_session.add(session)
        await db_session.flush()

    append_session_message(session, "user", message.text)
    updated_messages = list(session.raw_messages)
    await message.bot.send_chat_action(message.chat.id, "typing")
    # Weather is handled deterministically so a provider/model tool decision
    # cannot turn a simple forecast request into a vague AI refusal.
    events_result = await db_session.execute(select(ImportantEvent).where(ImportantEvent.user_id == user.id).order_by(ImportantEvent.occurred_at.desc()).limit(20))
    events = [{"title": event.title, "event_type": event.event_type, "importance": event.importance, "description": event.description} for event in events_result.scalars()]
    memory_for_reply = dict(user.memory or {})
    feedback = feedback_context(user.tech_stack)
    if feedback:
        memory_for_reply["response_feedback"] = feedback
    if events:
        memory_for_reply["important_events"] = events
    # Short social messages such as "как сам?" are not reliable semantic
    # queries. Recalling old vector memories for them makes the bot inject
    # unrelated topics into an otherwise normal reply.
    recalled = []
    if (
        len(message.text.strip()) >= config.MEMORY_AUTO_RECALL_MIN_CHARS
        or should_recall_context(message.text)
    ):
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
    # The visual summary is already stored in the conversation history.
    # Resend the binary image only for an explicit visual follow-up; otherwise
    # every later text message is incorrectly routed through the vision model.
    restored_media = []
    if previous_media and refers_to_previous_media(message.text):
        restored_media = await restore_session_media(message.bot, previous_media)
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
    # Vector memory is for the user's own durable context, not AI prose or
    # temporary research about third parties.
    await remember(db_session, user.id, message.text, source="explicit_memory" if explicit_fact else "user_message")

    try:
        await db_session.commit()
        await db_session.refresh(session)
    except Exception as e:
        logging.exception("Failed to save Telegram session user_id=%s session_id=%s", user.id, session.id)

