from utils.intent import explicit_memory_fact, is_web_request, is_youtube_request, should_search_web, youtube_query


def test_ordinary_messages_do_not_trigger_web_search():
    assert not should_search_web("Расскажи, как у тебя дела сегодня")
    assert not should_search_web("Я сегодня устал после работы")


def test_explicit_current_question_triggers_web_search():
    assert should_search_web("Какая сегодня погода в Москве?")
    assert should_search_web("Знаешь ли ты последние новости о SpaceX?")
    assert should_search_web("Подскажи актуальную цену iPhone")


def test_youtube_link_request_is_detected():
    assert is_youtube_request("скинь ссылку на ютуб про BMW")


def test_video_request_is_detected_without_youtube_word():
    assert is_youtube_request("покажи ролик про ремонт машины")


def test_web_request_is_detected_and_youtube_is_prioritized():
    assert is_web_request("проверь актуальную цену BMW")
    assert not is_web_request("найди ролик на ютубе про BMW")


def test_explicit_memory_fact_is_extracted():
    assert explicit_memory_fact("запомни, что у меня BMW") == "у меня BMW"


def test_youtube_query_removes_command_words():
    assert youtube_query("Найди ролик на ютубе про BMW E39") == "про BMW E39"
