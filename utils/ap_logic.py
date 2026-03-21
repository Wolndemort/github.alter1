import json
from openai import AsyncOpenAI
from config import config
import logging


client = AsyncOpenAI(
    base_url="https://openrouter.ai",
    api_key=config.GEMINI_API_KEY.get_secret_value(),
)


GOLDEN_PROMT = """
Ты — ядро долгосрочной памяти ИИ-ассистента ALTER. Твоя задача: проанализировать диалог и 
извлечь ключевые факты о пользователе для обновления его "цифрового слепка".

ОСНОВНЫЕ КАТЕГОРИИ:
1. health_sport: (травмы, тренировки, анализы, питание, самочувствие).
2. skills_career: (прогресс в кодинге, изученные темы, рабочие задачи, планы).
3. psycho_vibe: (настроение, уровень энергии, страхи, мотивация).
4. bio_prefs: (рост, вес, город, размеры одежды, любимая еда).
5. social_links: (семья, друзья, отношения, важные имена).

ПРАВИЛА:
- Используй лаконичные ключи на английском (snake_case).
- Строгий JSON. Без лишнего текста.
"""


async def summarize_session(messages: list) -> dict:
    dialogue_text = "\n".join([f"{m['role']}: {m['content']}" for m in messages])

    try:
        response = await client.chat.completions.create(
            model="google/gemini-2.0-flash-exp:free",  # Можно менять на любую (gpt-4o, claude-3)
            messages=[
                {"role": "system", "content": GOLDEN_PROMT},
                {"role": "user", "content": f"ДИАЛОГ ДЛЯ АНАЛИЗА:\n{dialogue_text}"}
            ],
            response_format={"type": "json_object"}
        )

        content = response.choices[0].message.content
        return json.loads(content)

    except Exception as e:
        logging.error(f"❌ OpenRouter Error: {e}")
        return {}
