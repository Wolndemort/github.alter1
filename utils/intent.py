import re

YOUTUBE_PATTERNS = (
    r"\byoutube\b", r"\b\u044e\u0442\u0443\u0431\b",
    r"\u0441\u043a\u0438\u043d\u044c.*\u0441\u0441\u044b\u043b", r"\u0434\u0430\u0439.*\u0441\u0441\u044b\u043b",
    r"\u043d\u0430\u0439\u0434\u0438.*(\u0440\u043e\u043b\u0438\u043a|\u0432\u0438\u0434\u0435\u043e)",
    r"\u043f\u043e\u043a\u0430\u0436\u0438.*(\u0440\u043e\u043b\u0438\u043a|\u0432\u0438\u0434\u0435\u043e)",
)
WEB_PATTERNS = (
    r"\b\u043d\u0430\u0439\u0434\u0438\b", r"\b\u043d\u0430\u0439\u0442\u0438\b", r"\u043f\u0440\u043e\u0432\u0435\u0440\u044c",
    r"\u0430\u043a\u0442\u0443\u0430\u043b\u044c\u043d", r"\u043d\u043e\u0432\u043e\u0441\u0442", r"\u0446\u0435\u043d\u0430",
    r"\u043f\u043e\u0433\u043e\u0434\u0430", r"\u0440\u0430\u0441\u0441\u043a\u0430\u0436\u0438 (\u043e|\u043f\u0440\u043e)",
    r"\b\u0437\u043d\u0430\u0435\u0448\u044c\b", r"\b\u0447\u0442\u043e\s+\u0442\u0430\u043a\u043e\u0435\b",
    r"\b\u0447\u0442\u043e\s+\u0437\u0430\b", r"\b\u043a\u0442\u043e\s+(\u0442\u0430\u043a\u043e\u0439|\u0442\u0430\u043a\u0430\u044f)\b",
    r"\b\u043c\u043e\u0436\u043d\u043e\s+\u043b\u0438\b", r"\b\u043f\u0440\u0430\u0432\u0434\u0430\s+\u043b\u0438\b",
    r"\b\u043e\u0442\u0437\u044b\u0432", r"\b\u0441\u043e\u0441\u0442\u0430\u0432", r"\b\u0438\u043d\u0433\u0440\u0435\u0434\u0438\u0435\u043d\u0442",
)

def _matches(text, patterns):
    value = (text or "").casefold().replace("\u0451", "\u0435")
    return any(re.search(pattern, value) for pattern in patterns)

def is_youtube_request(text):
    return _matches(text, YOUTUBE_PATTERNS)


def youtube_query(text):
    """Return the subject of a YouTube request instead of the whole sentence."""
    value = (text or "").strip()
    value = re.sub(r"https?://(?:www\.)?youtube\.com\S+", "", value, flags=re.I)
    value = re.sub(r"\bна\s+ютуб(?:е|а)?\b|\b(?:youtube|ютуб(?:е|а)?)\b", "", value, flags=re.I)
    value = re.sub(r"\b(?:найди|найти|покажи|скинь|дай|пришли|посоветуй|включи|скачай)\b", "", value, flags=re.I)
    value = re.sub(r"\b(?:ссылку|ссылка|ролик|ролика|видео|песню|песня|трек|музыку|аудио)\b", "", value, flags=re.I)
    value = re.sub(r"\s+", " ", value).strip(" .,!?-:\n\t")
    return value or (text or "").strip()

def is_web_request(text):
    return _matches(text, WEB_PATTERNS) and not is_youtube_request(text)


def should_search_web(text):
    """Decide whether a normal message is substantial enough for live search.

    This is intentionally a search-first gate, not a list of factual keywords.
    Only greetings, short small talk, and explicit personal-memory statements
    bypass the web search.
    """
    value = re.sub(r"\s+", " ", (text or "").casefold()).strip()
    if len(value) < 10:
        return False
    if is_youtube_request(value):
        return False
    if re.match(r"^(?:запомни|запиши|сохрани|напомни)\b", value):
        return False
    casual = (
        r"^(?:привет|здравствуй|добрый (?:день|вечер|утро)|как дела|спасибо|пока|до свидания|окей|ок|понял|понятно)[!.?]*$",
    )
    return not any(re.fullmatch(pattern, value) for pattern in casual)

def explicit_memory_fact(text):
    match = re.search(r"(?:\u0437\u0430\u043f\u043e\u043c\u043d\u0438|\u0437\u0430\u043f\u0438\u0448\u0438|\u0441\u043e\u0445\u0440\u0430\u043d\u0438)\s*(?:[,!:;-]\s*)?(?:\u0447\u0442\u043e\s+)?(.+)", text or "", re.I)
    return match.group(1).strip(" .,!\\n") if match else None
