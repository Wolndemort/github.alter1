from utils.request_routing import classify_request


def test_short_russian_chat_uses_streamable_fast_route():
    route = classify_request("Привет, как дела?")
    assert route.kind == "chat"
    assert route.initial_status == "analyzing"
    assert route.streamable


def test_planning_request_exposes_planning_state():
    route = classify_request("Составь план запуска проекта")
    assert route.kind == "planning"
    assert route.initial_status == "planning"
    assert route.streamable


def test_current_web_request_uses_search_route():
    route = classify_request("Найди актуальную цену iPhone")
    assert route.kind == "web"
    assert route.initial_status == "searching"
    assert not route.streamable


def test_search_synonym_uses_search_route():
    route = classify_request("Поищи в интернете отзывы о новом телефоне")
    assert route.kind == "web"
    assert route.initial_status == "searching"
    assert not route.streamable


def test_person_question_is_not_forced_into_web_tools():
    route = classify_request("Знает ли ALTER Кинана Джеймса?")
    assert route.kind == "chat"
    assert route.streamable
