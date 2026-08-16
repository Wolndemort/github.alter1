from utils.intent import conversation_mode, is_web_request, should_search_web
from utils.quality import has_language_mismatch
from utils.request_routing import classify_request


def test_russian_slang_stays_in_conversation_mode():
    assert conversation_mode("Мне капец как тревожно, побудь рядом") == "support"


def test_game_build_questions_require_factual_search():
    question = "В Ghost of Tsushima нормальный билд: оберег Инари на урон и доспехи Саругами?"
    assert is_web_request(question)
    assert should_search_web(question)
    assert classify_request("Йо, что по плану на сегодня?").streamable


def test_russian_current_question_requires_web_intent():
    assert should_search_web("Проверь, что там сегодня по ценам на айфон")
    assert not should_search_web("Да ну, это вообще жесть")


def test_russian_request_rejects_english_answer():
    assert has_language_mismatch("Sure, let's make a plan.", "Помоги мне составить план")
