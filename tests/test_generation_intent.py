from utils.generation_intent import generation_kind


def test_generation_intent_routes_text_and_transcribed_voice():
    assert generation_kind("Создай красивое фото девушки") == "image"
    assert generation_kind("Нарисуй ночной город") == "image"
    assert generation_kind("Оживи это изображение") == "video"
    assert generation_kind("Сгенерируй короткий ролик") == "video"
    assert generation_kind("Проанализируй эту фотографию") is None
