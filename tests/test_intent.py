from utils.intent import explicit_memory_fact, is_local_search_request, is_web_request, is_youtube_request, should_prefetch_web, should_recall_context, should_search_web, youtube_query


def test_ordinary_messages_do_not_trigger_web_search():
    assert not should_search_web("Расскажи, как у тебя дела сегодня")
    assert not should_search_web("Я сегодня устал после работы")


def test_explicit_current_question_triggers_web_search():
    assert should_search_web("Какая сегодня погода в Москве?")
    assert should_search_web("Знаешь ли ты последние новости о SpaceX?")
    assert should_search_web("Подскажи актуальную цену iPhone")


def test_search_synonyms_trigger_web_search():
    for request in (
        "Поищи в интернете отзывы о BMW",
        "Поискать актуальную цену iPhone",
        "Погугли новости про SpaceX",
        "Проведи поиск лучших наушников",
        "Глянь в интернете, кто сегодня выступает",
    ):
        assert should_search_web(request), request


def test_knowledge_questions_prefetch_web_without_explicit_search_command():
    for request in ("Знаешь ли ты игру Hades?", "Расскажи про сериал Severance", "Что это за компания Nvidia?"):
        assert should_prefetch_web(request), request
    assert not should_prefetch_web("Мне сегодня грустно, побудь со мной")


def test_directory_search_is_reserved_for_local_requests():
    assert is_local_search_request("Где рядом со мной хорошее кафе?")
    assert is_local_search_request("Как добраться до магазина?")
    assert not is_local_search_request("Знаешь ли ты игру Hades?")


def test_youtube_link_request_is_detected():
    assert is_youtube_request("скинь ссылку на ютуб про BMW")


def test_video_request_is_detected_without_youtube_word():
    assert is_youtube_request("покажи ролик про ремонт машины")


def test_web_request_is_detected_and_youtube_is_prioritized():
    assert is_web_request("проверь актуальную цену BMW")
    assert not is_web_request("найди ролик на ютубе про BMW")


def test_explicit_memory_fact_is_extracted():
    assert explicit_memory_fact("запомни, что у меня BMW") == "у меня BMW"


def test_common_memory_questions_trigger_context_recall():
    for request in ("Ты меня помнишь?", "Что ты обо мне знаешь?", "Расскажи, что ты обо мне знаешь"):
        assert should_recall_context(request), request


def test_natural_continuations_trigger_context_recall():
    for request in ("Давай дальше", "Где мы остановились?", "Я вернулся", "А что с концовкой игры?"):
        assert should_recall_context(request), request


def test_youtube_query_removes_command_words():
    assert youtube_query("Найди ролик на ютубе про BMW E39") == "про BMW E39"
