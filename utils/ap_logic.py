import json
from google import genai
from config import config
import re


client = genai.Client(
    api_key=config.GEMINI_API_KEY.get_secret_value(),
    http_options={'api_version': 'v1'}
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
    prompt = f"{GOLDEN_PROMT}\n\nДИАЛОГ ДЛЯ АНАЛИЗА:\n{dialogue_text}"

    try:
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=prompt
        )

        text = response.text
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {}
    except Exception as e:
        print(f"❌ Ошибка Gemini: {e}")
        return {}


