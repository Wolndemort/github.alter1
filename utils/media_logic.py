import base64
import logging

from config import config
from utils.ap_logic import client
from utils.prompts import MEDIA_SYSTEM_PROMPT


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
        messages = [{"role": "system", "content": MEDIA_SYSTEM_PROMPT + context_note}]
        for turn in (conversation_context or [])[-12:]:
            if turn.get("role") in {"user", "assistant"} and turn.get("content"):
                messages.append({"role": turn["role"], "content": str(turn["content"])})
        messages.append({"role": "user", "content": content})
        models = [config.OPENROUTER_MODEL]
        if config.OPENROUTER_FALLBACK_MODEL and config.OPENROUTER_FALLBACK_MODEL not in models:
            models.append(config.OPENROUTER_FALLBACK_MODEL)
        if config.OPENROUTER_FALLBACK_MODEL_2 and config.OPENROUTER_FALLBACK_MODEL_2 not in models:
            models.append(config.OPENROUTER_FALLBACK_MODEL_2)
        response = None
        for model in models:
            try:
                response = await client.chat.completions.create(model=model, messages=messages, max_tokens=config.MAX_MEDIA_OUTPUT_TOKENS)
                break
            except Exception:
                logging.exception("Media model failed: %s", model)
        if response is None:
            raise RuntimeError("all media models failed")
        return response.choices[0].message.content or "Не смог разобрать материал."
    except Exception:
        logging.exception("Media analysis error")
        return "Не удалось проанализировать файл. Проверь формат и ключ модели."
