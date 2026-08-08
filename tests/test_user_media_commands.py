from handlers.user_handlers import media_generation_requested


def test_natural_russian_photo_edit_caption_is_generation_command():
    assert media_generation_requested("Редактируй фото, надень шляпу ему на голову")
    assert media_generation_requested("Оживи это фото")


def test_media_edit_actions_are_generation_commands():
    for prompt in (
        "/edit add a hat",
        "измени фон на море",
        "сделай его в стиле комикса",
        "добавь очки",
        "убери человека справа",
        "замени небо",
        "переодень в костюм",
    ):
        assert media_generation_requested(prompt), prompt


def test_visual_questions_stay_on_analysis_path():
    for prompt in ("Что на фото?", "Опиши изображение", "кто здесь изображён?"):
        assert not media_generation_requested(prompt), prompt
