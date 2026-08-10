"""Small deterministic guardrail for ALTER's human-facing behavior.

These cases do not call a provider. They make the intended character explicit
so prompt/routing changes cannot silently remove the product behavior.
"""

from utils.memory_facts import extract_user_facts
from utils.prompts import ALTER_CHARACTER_PROMPT, ALTER_INTELLIGENCE_PROMPT
from utils.quality import assess_reply


SCENARIOS = (
    ("casual", "Бро, что-то совсем нет сил", "признай состояние"),
    ("decision", "Мне выбрать вариант А или Б?", "критерий выбора"),
    ("planning", "Помоги разложить запуск проекта", "первый шаг"),
    ("memory", "Вернись к тому, что мы обсуждали", "восстанови контекст"),
    ("conflict", "Я хочу всё успеть, но времени нет", "противоречие"),
)


def test_character_benchmark_covers_core_human_situations():
    text = ALTER_CHARACTER_PROMPT + "\n" + ALTER_INTELLIGENCE_PROMPT
    for _, _, expected in SCENARIOS:
        assert expected in text


def test_explicit_style_preferences_are_remembered():
    assert extract_user_facts("Отвечай мне короче и без официоза") ["preferences"]["response_style"] == "casual"
    assert extract_user_facts("Говори прямо") ["preferences"]["response_style"] == "direct"


def test_benchmark_rejects_internal_planning_but_allows_short_living_reply():
    assert "internal_details" in assess_reply("Анализ: сначала нужно понять запрос.").issues
    assert assess_reply("Смотри, тут лучше начать с первого шага.").score == 100
