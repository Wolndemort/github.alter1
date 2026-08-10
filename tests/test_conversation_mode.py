from utils.intent import conversation_mode


def test_conversation_mode_covers_alter_core_situations():
    assert conversation_mode("Бро, мне очень тяжело и нет сил") == "support"
    assert conversation_mode("Что лучше выбрать: А или Б?") == "decision"
    assert conversation_mode("Составь план запуска и выдели шаги") == "planning"
    assert conversation_mode("Вернись к тому, что мы обсуждали") == "continuation"
    assert conversation_mode("Как прошёл твой день?") == "conversation"
