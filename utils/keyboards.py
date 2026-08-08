from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

MEMORY_BUTTON = "\U0001f9e0 \u041f\u0430\u043c\u044f\u0442\u044c"
NEW_SESSION_BUTTON = "\U0001f195 \u041d\u043e\u0432\u044b\u0439 \u0440\u0430\u0437\u0433\u043e\u0432\u043e\u0440"
REMINDERS_BUTTON = "\u23f0 \u041d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u044f"
CHECKINS_BUTTON = "\U0001f4ad Check-in"
HELP_BUTTON = "\u2753 \u041f\u043e\u043c\u043e\u0449\u044c"
SETTINGS_BUTTON = "⚙️ Настройки ALTER"
SETTINGS_BACK_BUTTON = "⬅️ В главное меню"
VOICE_BUTTON = "\U0001f399\ufe0f \u0413\u043e\u043b\u043e\u0441\u043e\u0432\u044b\u0435"
VOICE_ON_BUTTON = "\U0001f50a \u0412\u043a\u043b\u044e\u0447\u0438\u0442\u044c \u0433\u043e\u043b\u043e\u0441\u043e\u0432\u044b\u0435"
VOICE_OFF_BUTTON = "\U0001f507 \u0412\u044b\u043a\u043b\u044e\u0447\u0438\u0442\u044c \u0433\u043e\u043b\u043e\u0441\u043e\u0432\u044b\u0435"
BUY_SUBSCRIPTION_BUTTON = "\U0001f4b3 \u041a\u0443\u043f\u0438\u0442\u044c \u043f\u043e\u0434\u043f\u0438\u0441\u043a\u0443"
CABINET_BUTTON = "\U0001f464 \u041a\u0430\u0431\u0438\u043d\u0435\u0442"
STATUS_BUTTON = "\u2139\ufe0f \u0421\u0442\u0430\u0442\u0443\u0441"
USAGE_BUTTON = "\U0001f4ca \u041b\u0438\u043c\u0438\u0442\u044b"
SUPPORT_BUTTON = "\U0001f198 \u041f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0430"
BACK_BUTTON = "\u2b05\ufe0f \u041d\u0430\u0437\u0430\u0434"
AUTO_RENEW_ON_BUTTON = "\U0001f501 \u0412\u043a\u043b\u044e\u0447\u0438\u0442\u044c \u0430\u0432\u0442\u043e\u043f\u0440\u043e\u0434\u043bение"
AUTO_RENEW_OFF_BUTTON = "\u23f8\ufe0f \u0412\u044b\u043a\u043b\u044e\u0447\u0438\u0442\u044c \u0430\u0432\u0442\u043e\u043f\u0440\u043e\u0434\u043bение"
UNLINK_CARD_BUTTON = "\U0001f4b3 \u041e\u0442\u0432\u044fзать карту"


def memory_categories_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="identity"), KeyboardButton(text="goals_habits")],
            [KeyboardButton(text="skills_career"), KeyboardButton(text="interests_hobbies")],
            [KeyboardButton(text="open_loops"), KeyboardButton(text="\u2b05\ufe0f \u041d\u0430\u0437\u0430\u0434")],
        ], resize_keyboard=True,
    )


def memory_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=MEMORY_BUTTON), KeyboardButton(text=NEW_SESSION_BUTTON)],
            [KeyboardButton(text=REMINDERS_BUTTON), KeyboardButton(text=SETTINGS_BUTTON)],
            [KeyboardButton(text=BUY_SUBSCRIPTION_BUTTON), KeyboardButton(text=CABINET_BUTTON)],
            [KeyboardButton(text=STATUS_BUTTON), KeyboardButton(text=USAGE_BUTTON)],
            [KeyboardButton(text=SUPPORT_BUTTON), KeyboardButton(text=HELP_BUTTON)],
            [KeyboardButton(text="/faq"), KeyboardButton(text="/weather")],
            [KeyboardButton(text="/calendar_connect"), KeyboardButton(text="/calendar")],
            [KeyboardButton(text="/calendar_add"), KeyboardButton(text="/new_session")],
            [KeyboardButton(text="/memory"), KeyboardButton(text="/forget")],
            [KeyboardButton(text="/clear_memory"), KeyboardButton(text="/clear_context")],
            [KeyboardButton(text="/remind"), KeyboardButton(text="/reminders")],
            [KeyboardButton(text="/cancel_reminder"), KeyboardButton(text="/checkins_on")],
            [KeyboardButton(text="/checkins_off"), KeyboardButton(text="/settings")],
            [KeyboardButton(text="/status"), KeyboardButton(text="/usage")],
            [KeyboardButton(text="/voice_on"), KeyboardButton(text="/voice_off")],
            [KeyboardButton(text="/buy"), KeyboardButton(text="/help")],
        ], resize_keyboard=True,
        input_field_placeholder="\u0412\u044b\u0431\u0435\u0440\u0438 \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u0435 \u0438\u043b\u0438 \u043d\u0430\u043f\u0438\u0448\u0438 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435",
    )


def cabinet_keyboard(auto_renew: bool = False, has_card: bool = False) -> ReplyKeyboardMarkup:
    renewal_button = AUTO_RENEW_OFF_BUTTON if auto_renew else AUTO_RENEW_ON_BUTTON
    rows = [[KeyboardButton(text=BUY_SUBSCRIPTION_BUTTON)], [KeyboardButton(text=renewal_button)]]
    if has_card:
        rows.append([KeyboardButton(text=UNLINK_CARD_BUTTON)])
    rows.append([KeyboardButton(text=SUPPORT_BUTTON), KeyboardButton(text=BACK_BUTTON)])
    return ReplyKeyboardMarkup(
        keyboard=rows, resize_keyboard=True,
        input_field_placeholder="Выбери действие",
    )


def settings_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=CHECKINS_BUTTON), KeyboardButton(text=VOICE_BUTTON)],
            [KeyboardButton(text=SETTINGS_BACK_BUTTON)],
        ], resize_keyboard=True,
    )


def voice_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=VOICE_ON_BUTTON), KeyboardButton(text=VOICE_OFF_BUTTON)],
            [KeyboardButton(text="\u2b05\ufe0f \u041d\u0430\u0437\u0430\u0434")],
        ], resize_keyboard=True,
    )


def media_actions_keyboard() -> InlineKeyboardMarkup:
    """Human-readable actions shown under every Telegram media turn."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔎 Разобрать", callback_data="media:analyze")],
        [InlineKeyboardButton(text="✨ Улучшить фото", callback_data="media:improve")],
        [InlineKeyboardButton(text="🎬 Оживить видео", callback_data="media:animate")],
    ])
