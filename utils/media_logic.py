import base64
import json
import logging

from config import config
from utils.ap_logic import chat_with_fallback, chat_with_tools, client
from utils.prompts import MEDIA_SYSTEM_PROMPT, MEMORY_POLICY_PROMPT, PUBLIC_RESPONSE_POLICY
from utils.quality import has_internal_leak


async def generate_media_reply(
    prompt: str,
    media: list[tuple[str, bytes]],
    conversation_context: list | None = None,
    memory: dict | None = None,
    search_results: list[dict] | None = None,
) -> str:
    content = [{"type": "text", "text": prompt or "Проанализируй этот материал и ответь по-русски."}]
    if search_results:
        sources = "\nАктуальные результаты поиска — используй их только если они относятся к вопросу пользователя:\n" + "\n".join(
            f"- {item.get('title')}: {item.get('content', '')[:1200]} ({item.get('url')})"
            for item in search_results
        )
        content[0]["text"] += sources
    for media_type, data in media:
        encoded = base64.b64encode(data).decode("ascii")
        content.append({"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{encoded}"}})
    try:
        context_note = ""
        if conversation_context or memory:
            context_note = (
                "\nЭто продолжение одного диалога. Учитывай контекст и не начинай разговор заново. "
                f"Память пользователя: {memory or {}}"
            )
        messages = [{"role": "system", "content": MEDIA_SYSTEM_PROMPT + "\n\n" + MEMORY_POLICY_PROMPT + "\n\n" + PUBLIC_RESPONSE_POLICY + context_note}]
        for turn in (conversation_context or [])[-12:]:
            if turn.get("role") in {"user", "assistant"} and turn.get("content"):
                messages.append({"role": turn["role"], "content": str(turn["content"])})
        messages.append({"role": "user", "content": content})
        response = await chat_with_tools(messages, max_tokens=config.MAX_MEDIA_OUTPUT_TOKENS)
        answer = response.choices[0].message.content or "Не смог разобрать материал."
        if len(answer) > 3000 or has_internal_leak(answer):
            logging.warning("Rejecting oversized media reply as possible reasoning leak: chars=%d", len(answer))
            return "Я получил материал, но не смог безопасно сформулировать краткий ответ. Попробуй ещё раз."
        return answer
    except Exception:
        logging.exception("Media analysis error")
        return "Не удалось проанализировать файл. Проверь формат и ключ модели."


async def extract_visual_context(
    prompt: str,
    media: list[tuple[str, bytes]],
) -> dict:
    """Create a compact, factual visual summary for future turns."""
    content = [{
        "type": "text",
        "text": (
            "Верни только JSON без markdown. Опиши исключительно то, что реально "
            "видно на изображении: предметы, одежду, цвета, стиль, посадку и важные "
            "детали. Не определяй личность, возраст, бренд или настроение без "
            "надёжных визуальных оснований. Формат: {\"items\":[], \"colors\":[], "
            "\"style\":[], \"fit\":[], \"details\":[]}. Запрос пользователя: "
            + (prompt or "анализ изображения")
        ),
    }]
    for media_type, data in media:
        encoded = base64.b64encode(data).decode("ascii")
        content.append({"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{encoded}"}})
    try:
        response = await chat_with_fallback(
            [{"role": "system", "content": "Ты аккуратный визуальный каталогизатор."}, {"role": "user", "content": content}],
            max_tokens=180,
        )
        raw = (response.choices[0].message.content or "{}").strip().strip("` ")
        if raw.startswith("json"):
            raw = raw[4:].strip()
        result = json.loads(raw)
        return result if isinstance(result, dict) else {}
    except Exception:
        logging.exception("Visual context extraction failed")
        return {}
