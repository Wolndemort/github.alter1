import random

from utils.ap_logic import chat_with_fallback


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


async def generate_contextual_checkin(
    name: str,
    context: str | None = None,
    recent_messages: list | None = None,
    memory: dict | None = None,
) -> str:
    """Generate one natural follow-up question using the user's actual context."""
    prompt = {
        "name": name or "",
        "topic": (context or "")[:500],
        "memory": memory or {},
        "recent_messages": (recent_messages or [])[-20:],
    }
    messages = [
        {
            "role": "system",
            "content": (
                "Ты — живой личный ассистент. Сформулируй один короткий, естественный "
                "вопрос для мягкого follow-up по контексту пользователя. Учитывай, "
                "что именно он планировал, обсуждал или переживал. Не используй "
                "шаблонные фразы вроде «как всё прошло?», если можно спросить "
                "конкретнее. Не придумывай события и не ставь диагнозы. Верни "
                "только один вопрос на русском, без обращения, пояснений и списков."
            ),
        },
        {"role": "user", "content": str(prompt)},
    ]
    try:
        response = await chat_with_fallback(messages, max_tokens=120)
        result = (response.choices[0].message.content or "").strip().strip('"“”')
        if result:
            return result[:500]
    except Exception:
        pass
    return contextual_checkin(name, context)


def random_checkin() -> str:
    return contextual_checkin("")
