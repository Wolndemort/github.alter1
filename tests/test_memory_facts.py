from utils.memory_facts import extract_user_facts


def test_extracts_identity_location_work_and_learning():
    facts = extract_user_facts("Меня зовут Адам. Я живу в Москве. Я работаю в дизайне. Я изучаю Python")
    assert facts == {
        "identity": {"name": "Адам", "city": "Москве"},
        "skills_career": {"job": "дизайне"},
        "education": {"focus": "Python"},
    }


def test_name_does_not_absorb_following_clause():
    assert extract_user_facts("Меня зовут Адам и я работаю в дизайне") ["identity"]["name"] == "Адам"


def test_extracts_common_work_and_activity_phrasings():
    facts = extract_user_facts("Моя сфера деятельности — дизайн. Я занимаюсь разработкой мобильных приложений")
    assert facts["skills_career"]["job"] == "разработкой мобильных приложений"


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


def test_extracts_social_travel_skills_projects_books_food_and_technology():
    facts = extract_user_facts("Мои друзья живут рядом. Я умею программировать. Я работаю над ALTER. Я был в Грузии. Я читаю Дюну. Я не ем мясо. Я пользуюсь Android")
    assert facts["social"]["friends"] == "живут рядом"
    assert facts["skills_career"]["skills"] == "программировать"
    assert facts["projects"]["current"] == "ALTER"
    assert facts["travel"]["places"] == "Грузии"
    assert facts["books"]["likes"] == "Дюну"
    assert facts["food_drinks"]["avoids"] == "мясо"
    assert facts["technology"]["devices"] == "Android"


def test_extracts_age_language_colleagues_religion_values_and_finance():
    facts = extract_user_facts("Мне  thirty лет")
    assert facts == {}
    facts = extract_user_facts("Мне 30 лет. Я говорю на русском. Мои коллеги хорошие. Я атеист. Для меня важно развитие. Я коплю на квартиру")
    assert facts["identity"]["age"] == "30"
    assert facts["identity"]["language"] == "русском"
    assert facts["social"]["colleagues"] == "хорошие"
    assert facts["worldview"]["religion"] == "атеист"
    assert facts["worldview"]["values"] == "развитие"
    assert facts["finance"]["situation"] == "квартиру"
