from utils.intent import should_search_web


def test_local_and_price_questions_trigger_web_search_automatically():
    assert should_search_web("Где в Майкопе купить спорттовары?")
    assert should_search_web("Сейчас открыт какой-нибудь магазин?")
    assert should_search_web("Сколько стоит iPhone?")
