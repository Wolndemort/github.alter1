"""Cheap deterministic quality gate for generated replies."""

from dataclasses import dataclass
import re


PUBLIC_FALLBACK = "Понял тебя. Сформулируй, пожалуйста, что именно нужно сделать — отвечу коротко и по делу."
AI_FAILURE_FALLBACK = "Не удалось получить ответ прямо сейчас. Попробуй ещё раз через несколько секунд."


@dataclass(frozen=True)
class ReplyQuality:
    score: int
    issues: tuple[str, ...]


def _mojibake_score(value: str) -> int:
    return sum(value.count(marker) for marker in ("Р", "С", "вЂ", "в„", "в™"))


def repair_mojibake(value: str) -> str:
    """Repair common UTF-8 decoded as Windows-1251 without touching normal Cyrillic."""
    if _mojibake_score(value) < 3:
        return value
    try:
        candidate = value.encode("cp1251").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value
    return candidate if _mojibake_score(candidate) < _mojibake_score(value) else value


def has_internal_leak(reply: str) -> bool:
    """Return True when a model reply looks like exposed planning notes."""
    return "internal_details" in assess_reply(reply).issues


def _legacy_has_language_mismatch(reply: str, request: str) -> bool:
    """Detect an English answer to a clearly Russian request."""
    answer = re.findall(r"[A-Za-zА-Яа-яЁё]", reply or "")
    source = re.findall(r"[A-Za-zА-Яа-яЁё]", request or "")
    if not answer or not source:
        return False
    russian_chars = "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"
    russian_request = sum(char.lower() in russian_chars for char in source) / len(source)
    latin_answer = sum(char.isascii() and char.isalpha() for char in answer) / len(answer)
    if russian_request >= 0.35 and latin_answer >= 0.55:
        return True
    # Ukrainian-specific letters in a predominantly Russian answer are a
    # common provider failure mode. Cyrillic overlap alone is not enough to
    # classify a response as wrong-language.
    ukrainian_hits = sum((reply or "").casefold().count(char) for char in "іїєґ")
    russian_answer = sum((reply or "").casefold().count(char) for char in "абвгдеёжзийклмнопрстуфхцчшщъыьэюя")
    return russian_request >= 0.35 and ukrainian_hits >= 2 and ukrainian_hits > russian_answer * 0.02


def has_language_mismatch(reply: str, request: str) -> bool:
    """Detect English or Ukrainian answers to clearly Russian requests."""
    answer = [char for char in (reply or "") if char.isalpha()]
    source = [char for char in (request or "") if char.isalpha()]
    if not answer or not source:
        return False
    russian_chars = set("\u0430\u0431\u0432\u0433\u0434\u0435\u0451\u0436\u0437\u0438\u0439\u043a\u043b\u043c\u043d\u043e\u043f\u0440\u0441\u0442\u0443\u0444\u0445\u0446\u0447\u0448\u0449\u044a\u044b\u044c\u044d\u044e\u044f")
    russian_request = sum(char.casefold() in russian_chars for char in source) / len(source)
    latin_answer = sum(char.isascii() and char.isalpha() for char in answer) / len(answer)
    if russian_request >= 0.35 and latin_answer >= 0.55:
        return True
    ukrainian_hits = sum((reply or "").casefold().count(char) for char in "\u0456\u0457\u0454\u0491")
    russian_answer = sum((reply or "").casefold().count(char) for char in russian_chars)
    ukrainian_words = ("\u0433\u0430\0440\0430\0437\0434", "\u0434\u043e\043f\043e\043c\043e\0436\0443", "\u043f\0438\0442\0430\043d\043d\044f", "\u0432\0443\043b\0438\0446", "\u044f\043a\0449\043e", "\u0447\u0430\0441\0438")
    ukrainian_words = tuple(
        "".join(chr(code) for code in codes)
        for codes in (
            (0x0433, 0x0430, 0x0440, 0x0430, 0x0437, 0x0434),
            (0x0434, 0x043e, 0x043f, 0x043e, 0x043c, 0x043e, 0x0436, 0x0443),
            (0x043f, 0x0438, 0x0442, 0x0430, 0x043d, 0x043d, 0x044f),
            (0x0432, 0x0443, 0x043b, 0x0438, 0x0446),
            (0x044f, 0x043a, 0x0449, 0x043e),
            (0x0447, 0x0430, 0x0441, 0x0438),
        )
    )
    word_hit = any(word in (reply or "").casefold() for word in ukrainian_words)
    return russian_request >= 0.35 and ukrainian_hits >= 1 and word_hit and ukrainian_hits > russian_answer * 0.01


def sanitize_public_reply(reply: str) -> str:
    """Never expose prompts, roles, tool payloads, or planner notes to clients."""
    value = repair_mojibake(str(reply or "").strip())
    value = re.sub(r"</?answer(?:\s+[^>]*)?>", "", value, flags=re.IGNORECASE)
    value = re.sub(r"</?(?:internal|analysis|final)>", "", value, flags=re.IGNORECASE)
    value = value.strip()
    lowered = value.casefold()
    forbidden = (
        "<user_memory>", "</user_memory>", "system prompt", "developer message",
        "response policy", "tool_calls", "chain of thought", "internal reasoning",
        "не удалось получить ответ от ai. код запроса:",
    )
    return PUBLIC_FALLBACK if not value or any(marker in lowered for marker in forbidden) or has_internal_leak(value) else value


def assess_reply(reply: str, *, has_sources: bool = False) -> ReplyQuality:
    text = (reply or "").strip()
    lowered = text.casefold()
    issues: list[str] = []
    if not text:
        issues.append("empty")
    if len(text) > 12000:
        issues.append("too_long")
    if text.count("?") > 1:
        issues.append("too_many_questions")
    leaked_markers = (
        "tool_calls", '"status":', "system prompt", "developer message", "chain of thought",
        "we need to answer", "we need to browse", "let's do a search", "let's simulate",
        "as ai,", "as an ai", "search terms:", "we should use", "need to check",
        "internal reasoning", "internal notes", "final answer:",
        "the user just mentioned", "the user mentioned", "looking at the memory",
        "memory section in the instructions", "according to the rules",
        "the tools available", "the system expects", "i need to store",
        "i should use the memory", "but wait, the tools", "which means they just",
        "internal response mode", "the memory shows", "character guidelines",
        "key constraints", "first, i need to", "looking back at the history",
        "check memory for", "per guidelines", "noting their tone", "my role as alter",
        "the user is feeling", "the user just shifted", "important: don't",
        "the user says:", "we must respond", "per instructions", "according to flavor",
        "we should not ask", "we can respond", "they are expressing", "the user request",
        "we need to respond", "according to character rules", "according to alter behavior",
        "the user just says", "given instructions", "potential answer:", "thus response:",
        "let's craft", "we need context", "we should respond", "the last user message",
        "we need to obey", "earlier we were told", "the instruction", "we cannot",
        "we can ask", "we should ask", "the user wants", "i can ask",
    )
    reasoning_phrases = (
        "сначала проверю", "следует добавить", "нужно добавить", "ответ должен быть", "пользователь сказал", "пользователь написал",
        "я должен ответить", "нужно ответить пользователю", "следует ответить",
        "внутреннее рассуждение", "предыдущий диалог", "инструмент не нужен",
        "пользователь хочет", "пользователь просит", "сначала нужно понять",
    )
    # A single word such as «пользователь» is normal. Several planning phrases
    # together are a strong signal that the model exposed its working notes.
    planning_hits = sum(phrase in lowered for phrase in reasoning_phrases)
    if any(marker in lowered for marker in leaked_markers) or planning_hits >= 2 or re.search(r"(?:^|\n)\s*(?:анализ|рассуждение|план ответа)\s*:", lowered):
        issues.append("internal_details")
    if has_sources and "http" not in lowered and "source:" not in lowered and "источник" not in lowered and "источники" not in lowered:
        issues.append("missing_source_attribution")
    score = max(0, 100 - len(issues) * 25)
    return ReplyQuality(score=score, issues=tuple(issues))
