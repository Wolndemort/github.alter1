import json
import re
import logging
from datetime import datetime, timezone
from openai import AsyncOpenAI
from config import config

client = AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=(config.OPENROUTER_API_KEY or config.GEMINI_API_KEY).get_secret_value(), timeout=config.AI_TIMEOUT_SECONDS, max_retries=1)
MEMORY_CATEGORIES = {"identity", "health_sport", "food_drinks", "skills_career", "interests_hobbies", "goals_habits", "psycho_vibe", "relationships", "worldview", "politics", "preferences", "important_events", "open_loops"}
KEY_ALIASES = {"имя": "name", "возраст": "age", "город": "city", "работа": "job", "профессия": "job"}

def normalize_key(value):
    raw = str(value).strip().casefold().replace("-", "_").replace(" ", "_")
    return KEY_ALIASES.get(raw, re.sub(r"[^a-z0-9_]+", "_", raw).strip("_"))

def normalize_memory(value):
    if not isinstance(value, dict): return {}
    result = {}
    for category, facts in value.items():
        if category not in MEMORY_CATEGORIES: continue
        if isinstance(facts, dict): facts = {normalize_key(k): v for k, v in facts.items()}
        result[category] = facts
    return result

GOLDEN_PROMT = ("Извлекай факты только если пользователь явно сообщил их сам. Отдельно сохраняй будущие события, обещания ALTER вернуться к теме и незавершённые дела в open_loops; для них указывай title, follow_up_question и follow_up_at. follow_up_at заполняй только если время понятно, в ISO 8601 с часовым поясом; иначе оставляй пустым. Верни строгий JSON, ключи snake_case; "
                "категории: identity:; health_sport:; food_drinks:; skills_career:; interests_hobbies:; goals_habits:; "
                "psycho_vibe:; relationships:; worldview:; politics:; preferences:; important_events:; open_loops:. "
                "Не делай выводов и не профилируй.")

async def chat_with_fallback(messages, max_tokens=None):
    for model in filter(None, [config.OPENROUTER_MODEL, config.OPENROUTER_FALLBACK_MODEL, config.OPENROUTER_FALLBACK_MODEL_2]):
        try: return await client.chat.completions.create(model=model, messages=messages, max_tokens=max_tokens or config.MAX_OUTPUT_TOKENS)
        except Exception: logging.exception("Chat model failed: %s", model)
    raise RuntimeError("No chat model configured")

async def summarize_session(messages):
    try:
        context = {"current_time": datetime.now(timezone.utc).isoformat(), "messages": messages}
        response = await chat_with_fallback([{"role": "system", "content": GOLDEN_PROMT}, {"role": "user", "content": json.dumps(context, ensure_ascii=False)}], config.MAX_MEMORY_OUTPUT_TOKENS)
        return normalize_memory(json.loads((response.choices[0].message.content or "{}").strip("` ").removeprefix("json").strip()))
    except Exception: return {}

async def generate_reply(messages, memory=None, search_results=None):
    try:
        system = f"Ты — ALTER, живой и внимательный собеседник. Отвечай по-русски естественно и кратко. Не выдумывай факты. Не повторяй факты из памяти дословно. Используй память только по теме. Если есть важная или незавершённая тема, иногда бережно возвращайся к ней. Задавай максимум один уместный уточняющий вопрос, не превращая разговор в анкету. Память: {json.dumps(normalize_memory(memory or {}), ensure_ascii=False)}"
        response = await chat_with_fallback([{"role": "system", "content": system}, *messages])
        return response.choices[0].message.content or "Не смог сформулировать ответ."
    except Exception: return "Не удалось получить ответ от AI."
