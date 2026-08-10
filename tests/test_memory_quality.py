from utils.memory_quality import is_memory_worthy, memory_reason


def test_accepts_stable_first_person_fact_for_both_clients():
    text = "Я живу в Москве и изучаю Python по вечерам"
    assert is_memory_worthy(text, "user_message")
    assert memory_reason(text) == "accepted"


def test_accepts_explicit_save_even_when_it_is_not_a_regex_fact():
    assert is_memory_worthy("Запомни: в рабочих сообщениях отвечай кратко", "user_message")


def test_rejects_questions_searches_greetings_and_third_party_noise():
    rejected = (
        "Привет, как дела у тебя сегодня?",
        "Найди актуальную цену на ноутбук и дай ссылки",
        "У него новая машина и он живёт в Казани",
        "Спасибо, всё понятно, продолжим завтра",
    )
    for text in rejected:
        assert not is_memory_worthy(text, "user_message")


def test_internal_explicit_sources_remain_supported():
    assert is_memory_worthy("A sufficiently long generated session summary", "conversation")
