from utils.ap_logic import normalize_memory
from utils.feedback_memory import feedback_context


def test_feedback_is_compact_and_keeps_only_actionable_examples():
    settings = {"reply_feedback": [
        {"rating": "positive", "answer": "Короткий ответ", "question": "Что делать?"},
        {"rating": "negative", "answer": "Слишком длинный ответ"},
        {"rating": "positive"},
        {"rating": "unknown", "answer": "ignore"},
    ]}
    assert feedback_context(settings) == [
        {"rating": "positive", "answer": "Короткий ответ", "question": "Что делать?"},
        {"rating": "negative", "answer": "Слишком длинный ответ"},
    ]


def test_feedback_survives_memory_prompt_normalization():
    value = normalize_memory({"response_feedback": [{"rating": "negative", "answer": "мимо"}]})
    assert value["response_feedback"][0]["rating"] == "negative"
