import json
import google.generativeai as genai
from config import config
import re
import os



# Конфигурация. Мы убрали api_version, так как библиотека сама выберет v1
# при использовании 'transport=rest' в последних версиях.
genai.configure(
    api_key=config.GEMINI_API_KEY.get_secret_value(),
    transport='rest'
)

# Инициализируем модель
model = genai.GenerativeModel('gemini-1.5-flash')

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
    """
    Отправляет лог сообщений в Gemini и получает структурированный JSON с фактами.
    """
    if not messages:
        return {}

    dialogue_text = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
    prompt = f"{GOLDEN_PROMT}\n\nДИАЛОГ ДЛЯ АНАЛИЗА:\n{dialogue_text}"

    try:
        # Генерация контента
        response = await model.generate_content_async(prompt)

        # Проверка на наличие текста в ответе
        if not response.text:
            print("⚠️ Gemini вернул пустой ответ")
            return {}

        text = response.text
        # Ищем JSON в ответе
        match = re.search(r'\{.*}', text, re.DOTALL)
        if match:
            return json.loads(match.group())

        print(f"⚠️ AI не вернул структурированный JSON. Ответ: {text[:100]}...")
        return {}

    except Exception as e:
        print(f"❌ Ошибка при работе с Gemini: {e}")
        return {}
