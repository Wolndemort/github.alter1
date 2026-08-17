import re

YOUTUBE_PATTERNS = (
    r"\byoutube\b", r"\b\u044e\u0442\u0443\u0431\b",
    r"\u0441\u043a\u0438\u043d\u044c.*\u0441\u0441\u044b\u043b", r"\u0434\u0430\u0439.*\u0441\u0441\u044b\u043b",
    r"\u043d\u0430\u0439\u0434\u0438.*(\u0440\u043e\u043b\u0438\u043a|\u0432\u0438\u0434\u0435\u043e)",
    r"\u043f\u043e\u043a\u0430\u0436\u0438.*(\u0440\u043e\u043b\u0438\u043a|\u0432\u0438\u0434\u0435\u043e)",
    r"\b(?:\u0441\u043a\u0438\u043d\u044c|\u043f\u0440\u0438\u0448\u043b\u0438|\u0432\u043a\u043b\u044e\u0447\u0438|\u0441\u043a\u0430\u0447\u0430\u0439)\b.*\b(?:\u043f\u0435\u0441\u043d\u044e|\u043f\u0435\u0441\u043d\u044e|\u043c\u0443\u0437\u044b\u043a\u0443|\u0442\u0440\u0435\u043a|\u0430\u0443\u0434\u0438\u043e)\b",
    r"\b(?:\u0441\u043a\u0438\u043d\u044c|\u043f\u0440\u0438\u0448\u043b\u0438|\u043d\u0430\u0439\u0434\u0438|\u043f\u043e\u043a\u0430\u0436\u0438)\b.*\b(?:\u0432\u0438\u0434\u0435\u043e|\u0440\u043e\u043b\u0438\u043a|\u043a\u043b\u0438\u043f)\b",
)
WEB_PATTERNS = (
    # Game builds and item stats are factual requests: do not answer these
    # from model memory because similar item names are easy to confuse.
    r"\b(?:билд\w*|оберег\w*|доспех\w*|оружи\w*|навык\w*|урон\w*|патч\w*|талант\w*|персонаж\w*)\b",
    r"\b(?:ghost\s+of\s+tsushima|призрак\s+цусимы|elden\s+ring|cyberpunk|witcher|игр\w*)\b.*\b(?:что\s+даёт|какой|какие|норм|собери|проверь|совет|билд|урон)\b",
    # Search synonyms must select the tool route; otherwise the model may
    # answer as if internet access were unavailable.
    r"\b\u043f\u043e\u0438\u0449\w*\b", r"\b\u043f\u043e\u0438\u0441\u043a\w*\b", r"\b(?:\u043f\u043e\u0433\u0443\u0433\u043b|\u0437\u0430\u0433\u0443\u0433\u043b)\w*\b",
    r"\b\u043f\u0440\u043e\u0432\u0435\u0434\u0438\s+\u043f\u043e\u0438\u0441\u043a\b", r"\b(?:\u0433\u043b\u044f\u043d\u044c|\u043f\u043e\u0441\u043c\u043e\u0442\u0440\u0438)\b.*\b(?:\u0432\s+)?\u0438\u043d\u0442\u0435\u0440\u043d\u0435\u0442\w*\b",
    r"\b\u043d\u0430\u0439\u0434\u0438\b", r"\b\u043d\u0430\u0439\u0442\u0438\b", r"\u043f\u0440\u043e\u0432\u0435\u0440\u044c",
    r"\u0430\u043a\u0442\u0443\u0430\u043b\u044c\u043d", r"\u043d\u043e\u0432\u043e\u0441\u0442", r"\u0446\u0435\u043d\u0430",
    r"\u043f\u043e\u0433\u043e\u0434\u0430", r"\u0440\u0430\u0441\u0441\u043a\u0430\u0436\u0438 (\u043e|\u043f\u0440\u043e)",
    r"\b\u0437\u043d\u0430\u0435\u0448\u044c\b", r"\b\u043f\u043e\u0434\u0441\u043a\u0430\u0436\u0438\b", r"\b\u0447\u0442\u043e\s+\u0442\u0430\u043a\u043e\u0435\b",
    r"\b\u0447\u0442\u043e\s+\u0437\u0430\b", r"\b\u043a\u0442\u043e\s+(\u0442\u0430\u043a\u043e\u0439|\u0442\u0430\u043a\u0430\u044f)\b",
    r"\b\u043c\u043e\u0436\u043d\u043e\s+\u043b\u0438\b", r"\b\u043f\u0440\u0430\u0432\u0434\u0430\s+\u043b\u0438\b",
    r"\b\u043e\u0442\u0437\u044b\u0432", r"\b\u0441\u043e\u0441\u0442\u0430\u0432", r"\b\u0438\u043d\u0433\u0440\u0435\u0434\u0438\u0435\u043d\u0442",
    r"\b\u0433\u0434\u0435\b.*\b(?:\u043a\u0443\u043f\u0438\u0442\u044c|\u043c\u0430\u0433\u0430\u0437\u0438\u043d|\u043e\u0442\u043a\u0440\u044b\u0442|\u0440\u044f\u0434\u043e\u043c|\u0430\u0434\u0440\u0435\u0441)\b",
    r"\b(?:\u0440\u044f\u0434\u043e\u043c|\u0430\u0434\u0440\u0435\u0441|\u0442\u0435\u043b\u0435\u0444\u043e\u043d)\b.*\b(?:\u043c\u0430\u0433\u0430\u0437|\u043e\u0440\u0433\u0430\u043d\u0438\u0437\u0430\u0446|\u043a\u043b\u0443\u0431|\u0430\u043a\u0430\u0434\u0435\u043c)\w*",
    r"\b\u0441\u043a\u043e\u043b\u044c\u043a\u043e\s+\u0441\u0442\u043e\u0438\u0442\b|\b\u0446\u0435\u043d\u0430\b",
    r"\b(?:\u043e\u0442\u043a\u0440\u044b\u0442|\u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442)\b.*\b(?:\u0441\u0435\u0439\u0447\u0430\u0441|\u0441\u0435\u0433\u043e\u0434\u043d\u044f|\u043c\u0430\u0433\u0430\u0437|\u043e\u0440\u0433\u0430\u043d\u0438\u0437\u0430\u0446)\w*",
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
    """Return whether the user explicitly asks for current/web information.

    This function is called for every ordinary message, and search results are
    later appended to the reply as URLs. Keep the decision tied to explicit
    web-intent patterns instead of searching every substantial message.
    """
    return is_web_request(text)


KNOWLEDGE_REQUEST_PATTERNS = (
    r"\b(?:знаешь\s+ли|кто\s+такой|кто\s+такая|что\s+такое|что\s+за|расскажи\s+(?:о|про)|что\s+можешь\s+сказать\s+о|объясни\s+(?:что|кто))\b",
    r"\b(?:игр[аеу]|фильм[аеу]|сериал[аеу]|книг[аеу]|аниме|манг[аеу]|групп[аеу]|песн[яе]|альбом[аеу]|акт[её]р|режисс[её]р|компани[яи]|програм|технолог|модел)\b",
)


def should_prefetch_web(text: str) -> bool:
    """Decide whether ALTER should search before asking the model to answer.

    This is intentionally conservative for casual/personal messages, while
    making factual requests deterministic instead of leaving search entirely
    to the model's tool-choice decision.
    """
    value = (text or "").casefold().replace("ё", "е")
    if is_web_request(value):
        return True
    if re.search(r"\b(?:как\s+дела|что\s+делаешь|побудь\s+со\s+мной|мне\s+грустно|я\s+(?:устал|устала|устал))\b", value):
        return False
    if any(re.search(pattern, value) for pattern in KNOWLEDGE_REQUEST_PATTERNS):
        return True
    # Keep this explicit as a safety net: these terms are frequently used in
    # short game questions where the broader knowledge classifier misses the
    # inflected form. Such answers must be grounded in current sources.
    return bool(re.search(r"\b(?:билд\w*|гайд\w*|сборк\w*|оберег\w*|оружи\w*|патч\w*|верси\w*)\b", value))


def is_local_search_request(text: str) -> bool:
    """Use directory search only when the user asks for a local place/service."""
    value = (text or "").casefold().replace("ё", "е")
    return bool(re.search(
        r"\b(?:рядом|поблизости|адрес|где\s+находится|как\s+добраться|маршрут|кафе|ресторан|магазин|аптека|банк|салон|организаци|заправк|отель|доставка)\w*\b",
        value,
    ))


CONTEXT_REFERENCE_PATTERNS = (
    r"\b(?:\u044d\u0442\u043e\u0442|\u044d\u0442\u0430|\u044d\u0442\u043e|\u0442\u043e\u0442|\u0442\u0430\u043c|\u043e\u043d|\u043e\u043d\u0430|\u043e\u043d\u0438|\u043d\u0438\u043c|\u043d\u0435\u0439|\u0441\u043d\u0438\u043c|\u0441\u043d\u0435\u0439)\b",
    r"\b(?:\u043f\u043e\u043c\u043d\u0438\u0448\u044c|\u043d\u0430\u043f\u043e\u043c\u043d\u0438|\u043a\u0430\u043a\s+\u0442\u0430\u043c|\u0447\u0442\u043e\s+\u0441|\u043f\u043e\s+\u043f\u043e\u0432\u043e\u0434\u0443|\u043d\u0430\u0441\u0447\u0451\u0442|\u043d\u0430\u0441\u0447\u0435\u0442|\u0432\u0435\u0440\u043d\u0451\u043c\u0441\u044f|\u0432\u0435\u0440\u043d\u0435\u043c\u0441\u044f|\u043f\u0440\u043e\u0434\u043e\u043b\u0436\u0438\u043c|вернись|прошл\w*|предыдущ\w*)\b",
    r"\b(?:remember|that|this|him|her|them|what\s+about|back\s+to)\b",
    r"\b(?:что\s+ты\s+обо\s+мне\s+помнишь|что\s+обо\s+мне\s+помнишь|что\s+ты\s+знаешь\s+обо\s+мне|что\s+помнишь\s+обо\s+мне)\b",
    r"\b(?:ты\s+меня\s+помнишь|ты\s+помнишь\s+меня|ты\s+меня\s+знаешь|ты\s+знаешь\s+меня|расскажи\s+что\s+ты\s+обо\s+мне\s+знаешь|что\s+ты\s+обо\s+мне\s+знаешь)\b",
    # Natural, elliptical continuations after a pause or relogin.
    r"\b(?:давай\s+(?:дальше|продолжим)|где\s+мы\s+остановились|на\s+чём\s+мы\s+остановились|я\s+(?:вернулся|вернулась)|мы\s+обсуждали|что\s+там\s+с|а\s+(?:концовк|сюжет|персонаж))\w*",
)


def should_recall_context(text):
    """Recall long-term context only for an explicit conversational reference."""
    return _matches(text, CONTEXT_REFERENCE_PATTERNS)


def conversation_mode(text: str) -> str:
    """Pick a lightweight response mode without an extra model round-trip."""
    value = (text or "").casefold()
    if should_recall_context(value):
        return "continuation"
    if re.search(r"\b(?:устал|тяжело|грустно|тревож|плохо|не вывожу|нет сил|бесит|разочарован)", value):
        return "support"
    if re.search(r"\b(?:выбрать|решить|сравни|стоит ли|лучше|за или|сомневаюсь)", value):
        return "decision"
    if re.search(r"\b(?:план|шаги|распиши|организуй|подготовь|составь|успеть|дедлайн)", value):
        return "planning"
    return "conversation"

def explicit_memory_fact(text):
    match = re.search(r"(?:\u0437\u0430\u043f\u043e\u043c\u043d\u0438|\u0437\u0430\u043f\u0438\u0448\u0438|\u0441\u043e\u0445\u0440\u0430\u043d\u0438)\s*(?:[,!:;-]\s*)?(?:\u0447\u0442\u043e\s+)?(.+)", text or "", re.I)
    return match.group(1).strip(" .,!\\n") if match else None


def do_not_remember(text: str) -> bool:
    """Respect an explicit request not to persist the current message."""
    value = (text or "").casefold()
    return bool(re.search(
        r"(?:не\s+(?:запоминай|запомни|сохраняй|сохрани)\b|"
        r"не\s+надо\s+(?:это\s+)?(?:запоминать|сохранять)|"
        r"не\s+сохраняй\s+это\b|"
        r"это\s+не\s+для\s+памяти)", value
    ))
