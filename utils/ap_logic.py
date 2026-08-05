import json
import re
import logging
from datetime import datetime, timezone
from openai import AsyncOpenAI
from config import config
from utils.metrics import increment
from utils.quality import assess_reply

client = AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=(config.OPENROUTER_API_KEY or config.GEMINI_API_KEY).get_secret_value(), timeout=config.AI_TIMEOUT_SECONDS, max_retries=0)
MEMORY_CATEGORIES = {"identity", "health_sport", "food_drinks", "skills_career", "interests_hobbies", "goals_habits", "psycho_vibe", "relationships", "worldview", "politics", "preferences", "important_events", "open_loops"}
KEY_ALIASES = {"имя": "name", "возраст": "age", "город": "city", "работа": "job", "профессия": "job"}
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Ищи актуальную информацию в интернете. Используй только для явного запроса пользователя или фактов, которые могут измениться.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Узнай текущую погоду или прогноз для города.",
            "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "youtube_search",
            "description": "Ищи видео или музыку на YouTube, только если пользователь просит видео, песню или ссылку.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        },
    },
]

COMPLEX_REQUEST_PATTERNS = (
    r"\b(?:сравни|сопоставь|проанализируй|разбери|объясни почему|почему|спланируй)\b",
    r"\b(?:составь|сделай)\b.*\b(?:план|стратег|сравн|разбор)\b",
    r"\b(?:архитектур|стратег|алгоритм|программ|код|дебаг|ошибк|рефактор)",
    r"\b(?:плюсы и минусы|за и против|пошагов|подробн|глубок)\b",
)


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

GOLDEN_PROMT = ("Извлекай факты только если пользователь явно сообщил их сам — о себе или своих планах. Не извлекай предположения, настроение, диагнозы или сведения о третьих лицах как факты пользователя. Если пользователь исправил старую информацию, используй новую. Отдельно сохраняй будущие события, обещания ALTER вернуться к теме и незавершённые дела в open_loops; для них указывай title, follow_up_question и follow_up_at. follow_up_at заполняй только если время понятно, в ISO 8601 с часовым поясом; иначе оставляй пустым. Верни строгий JSON, ключи snake_case; "
                "категории: identity:; health_sport:; food_drinks:; skills_career:; interests_hobbies:; goals_habits:; "
                "psycho_vibe:; relationships:; worldview:; politics:; preferences:; important_events:; open_loops:. "
                "Не делай выводов и не профилируй.")

def _request_text(messages) -> str:
    parts = []
    for message in messages or []:
        content = message.get("content") if isinstance(message, dict) else ""
        if isinstance(content, str) and message.get("role") == "user":
            parts.append(content)
    return " ".join(parts).casefold()


def _has_visual_input(messages) -> bool:
    """Whether the request contains OpenAI-compatible image content."""
    for message in messages or []:
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, list) and any(
            isinstance(item, dict) and item.get("type") in {"image_url", "input_image"}
            for item in content
        ):
            return True
    return False


def select_model_route(messages, task: str | None = None) -> list[str]:
    """Choose an inexpensive model for chat and a stronger one for hard work."""
    text = _request_text(messages)
    is_complex = task in {"reasoning", "planning"} or len(text) >= 700 or any(
        re.search(pattern, text) for pattern in COMPLEX_REQUEST_PATTERNS
    )
    if _has_visual_input(messages):
        free_models = [config.OPENROUTER_FREE_VISION_MODEL, config.OPENROUTER_FREE_VISION_MODEL_2]
    else:
        free_models = [config.OPENROUTER_FREE_MODEL, config.OPENROUTER_FREE_MODEL_2, config.OPENROUTER_FREE_MODEL_3]
    # Paid models are deliberately appended only after every configured free model.
    primary = free_models
    if config.OPENROUTER_ALLOW_PAID_FALLBACK:
        paid_models = ([config.OPENROUTER_REASONING_MODEL, config.OPENROUTER_MODEL]
                       if is_complex else [config.OPENROUTER_MODEL])
        primary += paid_models + [config.OPENROUTER_FALLBACK_MODEL, config.OPENROUTER_FALLBACK_MODEL_2]
    return list(dict.fromkeys(filter(None, primary)))


def _provider_status_code(error: Exception) -> int | None:
    value = getattr(error, "status_code", None) or getattr(error, "status", None)
    return value if isinstance(value, int) else None


async def chat_with_fallback(messages, max_tokens=None, task=None, models=None, **kwargs):
    for model in select_model_route(messages, task) if models is None else models:
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens or config.MAX_OUTPUT_TOKENS,
                **kwargs,
            )
        except Exception as error:
            status_code = _provider_status_code(error)
            increment("ai.model.failure", model=model, status=status_code or "exception")
            if status_code in {401, 403}:
                increment("ai.provider.permanent_failure", status=status_code)
                logging.error("Chat model rejected request: model=%s status=%s; fallback skipped", model, status_code)
                break
            if status_code == 404:
                logging.warning("Chat model is unavailable: model=%s status=404; paid fallback enabled=%s", model, config.OPENROUTER_ALLOW_PAID_FALLBACK)
            else:
                logging.exception("Chat model failed: %s", model)
            continue
        increment("ai.model.success", model=model)
        return response
    if not config.OPENROUTER_ALLOW_PAID_FALLBACK:
        raise RuntimeError("Бесплатная модель временно недоступна. Платный fallback отключён, чтобы не списывать деньги.")
    raise RuntimeError("No chat model configured")


async def execute_tool(name: str, arguments: dict) -> list | str:
    """Execute one model-selected tool behind a small, explicit allow-list."""
    if name == "web_search":
        from utils.web_search import search_web
        return await search_web(str(arguments.get("query") or ""))
    if name == "get_weather":
        from utils.weather import get_weather
        return await get_weather(str(arguments.get("city") or "Москва")) or "Погоду получить не удалось."
    if name == "youtube_search":
        from utils.youtube_search import search_youtube
        return await search_youtube(str(arguments.get("query") or ""))
    return "Неизвестный инструмент."


def validate_tool_result(name: str, result) -> tuple[str, object]:
    """Normalize tool output so the planner can distinguish success from empty data."""
    if isinstance(result, list) and not result:
        return "empty", f"Инструмент {name} ничего не нашёл. Измени запрос или выбери другой инструмент."
    if isinstance(result, str) and (not result.strip() or "не удалось" in result.casefold() or "неизвестный" in result.casefold()):
        return "error", result or f"Инструмент {name} вернул пустой результат."
    return "ok", result


async def plan_audio_request(text: str) -> dict:
    """Classify an audio request by meaning, without trigger-word lists."""
    prompt = (
        "Определи намерение пользователя. Верни только JSON вида "
        '{"download_audio": true|false, "query": "..."}. '
        "download_audio=true только если человек просит найти и отправить, включить или скачать "
        "аудио; обычный разговор о музыке — false. query — предмет поиска. "
        f"Текст: {text}"
    )
    try:
        response = await chat_with_fallback(
            [{"role": "system", "content": "Ты классификатор намерений без догадок."}, {"role": "user", "content": prompt}],
            max_tokens=100,
            task="planning",
        )
        value = json.loads((response.choices[0].message.content or "{}").strip("` ").removeprefix("json").strip())
        if not isinstance(value, dict):
            return {}
        return {"download_audio": bool(value.get("download_audio")), "query": str(value.get("query") or text).strip()}
    except Exception:
        increment("ai.audio_plan.failure")
        logging.exception("Audio intent planning failed")
        return {}


def _tool_call_payload(call) -> dict:
    """Convert an SDK tool call to the exact message shape expected by OpenAI."""
    if hasattr(call, "model_dump"):
        return call.model_dump(exclude_none=True)
    function = getattr(call, "function", None)
    return {
        "id": getattr(call, "id", ""),
        "type": "function",
        "function": {
            "name": getattr(function, "name", ""),
            "arguments": getattr(function, "arguments", "{}"),
        },
    }


async def chat_with_tools(messages, max_tokens=None, task=None):
    """Let the model call allowed tools, then continue with their results."""
    working = list(messages)
    max_rounds = max(1, min(config.TOOL_MAX_ROUNDS, 12))
    for _ in range(max_rounds):
        response = await chat_with_fallback(
            working,
            max_tokens=max_tokens,
            task=task,
            tools=TOOL_DEFINITIONS,
            tool_choice="auto",
        )
        message = response.choices[0].message
        tool_calls = getattr(message, "tool_calls", None) or []
        if not tool_calls:
            return response
        assistant = {
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": [_tool_call_payload(call) for call in tool_calls],
        }
        working.append(assistant)
        for call in tool_calls:
            function = getattr(call, "function", None)
            if function is None:
                continue
            try:
                arguments = json.loads(function.arguments or "{}")
            except (TypeError, ValueError):
                arguments = {}
            try:
                result = await execute_tool(function.name, arguments)
                status, result_for_model = validate_tool_result(function.name, result)
                increment(f"ai.tool.{status}", tool=function.name)
            except Exception:
                increment("ai.tool.failure", tool=function.name)
                logging.exception("Tool failed: %s", function.name)
                status, result_for_model = "error", "Инструмент временно недоступен. Измени запрос или продолжи без него."
            working.append({
                "role": "tool",
                "tool_call_id": getattr(call, "id", ""),
                "content": json.dumps({"status": status, "data": result_for_model}, ensure_ascii=False)[:12000],
            })
    increment("ai.tool.round_limit", limit=max_rounds)
    return await chat_with_fallback(working, max_tokens=max_tokens, task=task)

async def summarize_session(messages):
    try:
        context = {"current_time": datetime.now(timezone.utc).isoformat(), "messages": messages}
        response = await chat_with_fallback([{"role": "system", "content": GOLDEN_PROMT}, {"role": "user", "content": json.dumps(context, ensure_ascii=False)}], config.MAX_MEMORY_OUTPUT_TOKENS)
        return normalize_memory(json.loads((response.choices[0].message.content or "{}").strip("` ").removeprefix("json").strip()))
    except Exception: return {}

async def generate_reply(messages, memory=None, search_results=None):
    try:
        sources = ""
        if search_results:
            sources = "\nАктуальные результаты поиска (используй их, не выдумывай факты; сравнивай несколько источников, отмечай противоречия и не считай один сниппет доказательством):\n" + "\n".join(
                f"- {item.get('title')}: {item.get('content', '')[:1200]} ({item.get('url')})" for item in search_results
            )
        system = f"Ты — ALTER, живой и внимательный собеседник. Отвечай по-русски естественно и кратко. Не выдумывай факты. Не повторяй факты из памяти дословно. Используй память только по теме. Если есть важная или незавершённая тема, иногда бережно возвращайся к ней. Задавай максимум один уместный уточняющий вопрос, не превращая разговор в анкету. Сначала пойми смысл запроса, затем реши, нужен ли инструмент; не ориентируйся на конкретные ключевые фразы. Для актуальных фактов, погоды и поиска используй инструменты. После tool-вызова проверь поле status: при empty/error один раз измени запрос или выбери другой инструмент, а если данных всё равно нет — честно скажи об ограничении. Память: {json.dumps(normalize_memory(memory or {}), ensure_ascii=False)}{sources}"
        response = await chat_with_tools([{"role": "system", "content": system}, *messages])
        reply = response.choices[0].message.content or "Не смог сформулировать ответ."
        quality = assess_reply(reply, has_sources=bool(search_results))
        increment("ai.reply.quality", score=quality.score)
        for issue in quality.issues:
            increment("ai.reply.quality_warning", issue=issue)
        increment("ai.reply.success")
        return reply
    except Exception:
        increment("ai.reply.failure")
        return "Не удалось получить ответ от AI."
