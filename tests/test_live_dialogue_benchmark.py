"""Provider-independent dialogue benchmark for the ALTER voice contract."""

from utils.prompts import ALTER_CHARACTER_PROMPT, ALTER_INTELLIGENCE_PROMPT
from utils.quality import assess_reply


CASES = (
    ("Как-то всё навалилось", ("поддержка", "один вопрос")),
    ("Что выбрать — А или Б?", ("критерий", "вывод")),
    ("Составь план запуска", ("цель", "первый шаг")),
    ("Ты помнишь, о чём мы говорили?", ("продолжить", "контекст")),
    ("Ответь коротко и без официоза", ("стиль", "коротко")),
    ("Я хочу всё успеть за час", ("противоречие", "приоритет")),
)


def test_live_dialogue_cases_are_encoded_in_the_voice_contract():
    contract = (ALTER_CHARACTER_PROMPT + "\n" + ALTER_INTELLIGENCE_PROMPT).casefold()
    for _, expectations in CASES:
        assert any(term in contract for term in expectations), expectations


def test_normal_short_reply_has_no_quality_flags():
    examples = (
        "Смотри, тут лучше начать с первого шага.",
        "Да. Я бы выбрал второй вариант: он проще и быстрее.",
        "Понял. Что сейчас важнее всего не потерять?",
    )
    assert all(assess_reply(example).score == 100 for example in examples)
