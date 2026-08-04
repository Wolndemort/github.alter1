from handlers.user_handlers import format_memory
from utils.keyboards import memory_keyboard, memory_categories_keyboard


def test_memory_format_is_readable_for_nested_memory():
    result = format_memory({"skills_career": {"project": "ALTER"}, "goals": ["learn"]})
    assert "skills_career" in result
    assert "project: ALTER" in result
    assert "learn" in result


def test_memory_format_handles_empty_memory():
    assert "ничего" in format_memory({}).lower()


def test_minimal_keyboard_contains_memory_and_checkin_controls():
    labels = [button.text for row in memory_keyboard().keyboard for button in row]
    assert {"🧠 Память", "🆕 Новый разговор", "⏰ Напоминания", "💭 Check-in", "⚙️ Настройки", "🎙️ Голосовые", "❓ Помощь"} <= set(labels)


def test_main_keyboard_has_no_duplicate_buttons_and_expected_layout():
    keyboard = memory_keyboard().keyboard
    labels = [button.text for row in keyboard for button in row]
    assert len(labels) == len(set(labels))
    assert len(keyboard) == 4
    assert all(len(row) == 2 for row in keyboard[:-1])
    assert len(keyboard[-1]) == 1


def test_memory_categories_keyboard_contains_all_supported_user_choices():
    labels = [button.text for row in memory_categories_keyboard().keyboard for button in row]
    assert {"identity", "goals_habits", "skills_career", "interests_hobbies", "open_loops", "⬅️ Назад"} == set(labels)


def test_every_main_button_has_a_router_handler():
    from handlers.user_handlers import router

    callbacks = {handler.callback.__name__ for handler in router.message.handlers}
    assert {"button_memory", "button_new_session", "button_reminders", "button_checkins",
            "button_settings", "button_voice", "button_voice_on", "button_voice_off", "button_help"} <= callbacks
