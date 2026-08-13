from utils.capabilities import is_capabilities_request


def test_common_russian_capability_questions_are_detected():
    cases = (
        "Что умеет ALTER?", "Умеешь читать PDF?", "Можешь сравнить договоры?",
        "Можешь найти рядом аптеку?", "Можешь построить маршрут?",
        "Можешь изменить мой голос?", "Можешь вернуть изменённый файл?",
        "Умеешь анализировать видео?", "Как пользоваться OCR?",
    )
    assert all(is_capabilities_request(item) for item in cases)


def test_capability_questions_keep_routing_when_alter_is_the_subject():
    cases = (
        "умеет ли ALTER читать XLSX?",
        "умеет ли ALTER менять RTF?",
        "что ALTER умеет с видео и голосом?",
        "может ли ALTER вернуть изменённый PPTX?",
    )
    assert all(is_capabilities_request(item) for item in cases)
