from utils.memory_facts import extract_user_facts


def test_extracts_identity_location_work_and_learning():
    facts = extract_user_facts("Меня зовут Адам. Я живу в Москве. Я работаю в дизайне. Я изучаю Python")
    assert facts == {
        "identity": {"name": "Адам", "city": "Москве"},
        "skills_career": {"job": "дизайне"},
        "education": {"focus": "Python"},
    }


def test_classifies_preferences_into_useful_categories():
    assert extract_user_facts("Я люблю чёрную одежду") == {"style_clothing": {"style": "чёрную одежду"}}
    assert extract_user_facts("Мне нравится электронная музыка") == {"music": {"likes": "электронная музыка"}}
    assert extract_user_facts("Я предпочитаю фантастические фильмы") == {"films_series": {"likes": "фантастические фильмы"}}


def test_extracts_health_sport_family_and_events():
    facts = extract_user_facts("У меня аллергия на пыль. Я занимаюсь бегом. У меня есть брат. Мне предстоит экзамен")
    assert facts["health_sport"]["health"] == "аллергия на пыль"
    assert facts["health_sport"]["sport"] == "бегом"
    assert facts["family"]["family"] == "брат"
    assert facts["important_events"]["current"] == "экзамен"


def test_does_not_store_questions_or_third_person_facts():
    assert extract_user_facts("Какая музыка тебе нравится?") == {}
    assert extract_user_facts("У него новая машина") == {}
