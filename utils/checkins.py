import random


QUESTIONS = (
    "Как сегодня с энергией — получше или всё ещё тяжеловато?",
    "Удалось сегодня немного выдохнуть?",
    "Как настроение после последних дел — стало легче?",
    "Есть ощущение, что ты продвинулся вперёд?",
)


def contextual_checkin(name: str, context: str | None = None) -> str:
    """Мягкий вопрос только по фактам, которые пользователь уже сообщил."""
    greeting = f"{name}, " if name else ""
    if not context:
        return greeting + random.choice(QUESTIONS)
    templates = (
        "Ты недавно говорил про «{context}». Как там всё продвигается?",
        "Как у тебя с «{context}» — получилось сдвинуться с места?",
        "Ты упоминал «{context}». Есть новости?",
        "Как ты себя чувствуешь в контексте «{context}»?",
    )
    return greeting + random.choice(templates).format(context=context[:120])


def random_checkin() -> str:
    return contextual_checkin("")
