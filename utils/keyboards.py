from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

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
            [KeyboardButton(text=HELP_BUTTON)],
        ], resize_keyboard=True,
        input_field_placeholder="\u0412\u044b\u0431\u0435\u0440\u0438 \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u0435 \u0438\u043b\u0438 \u043d\u0430\u043f\u0438\u0448\u0438 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435",
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
