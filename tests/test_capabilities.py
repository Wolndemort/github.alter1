from utils.capabilities import CAPABILITIES_PROMPT, capabilities_reply, is_capabilities_request


def test_capabilities_request_is_detected_in_text_and_voice_transcript():
    assert is_capabilities_request("Что ты умеешь?")
    assert is_capabilities_request("Расскажи голосом, чем ты можешь помочь")
    assert is_capabilities_request("/help")
    assert not is_capabilities_request("Какая погода в Москве?")


def test_quota_and_usage_questions_are_capability_requests():
    assert is_capabilities_request("сколько кредитов стоит поиск?")
    assert is_capabilities_request("как пользоваться поиском?")


def test_inventory_does_not_advertise_unavailable_audio_products_as_available():
    assert is_capabilities_request("Что умеет ALTER?")
    assert is_capabilities_request("может ли он наложить шум дождя на голосовое?")
    for prompt in (
        "умеет ли он искать актуальные новости?",
        "может ли он добавить встречу в календарь?",
        "умеет ли ALTER запоминать мои предпочтения?",
        "можно ли создать видео?",
        "умеет ли он присылать уведомления?",
    ):
        assert is_capabilities_request(prompt), prompt
    reply = capabilities_reply()
    assert "звук дождя" in reply
    assert "Dubbing сейчас не подключены" in reply
    assert "Music Generation и Dubbing" in CAPABILITIES_PROMPT
    assert "Создание документов с нуля" in capabilities_reply()
    assert "DOCX, PDF, XLSX, PPTX" in capabilities_reply()
