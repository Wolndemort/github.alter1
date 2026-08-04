from urllib.parse import quote_plus
import re


def clean_product_query(query: str) -> str:
    """Remove conversational words before putting a product into a search URL."""
    value = query.strip()
    value = re.sub(r"\b(найди|поищи|подбери|покажи|мне|нужна|нужен|нужно|купить|на|в)\b", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"\b(wildberries|вб|вайldберриз|вайлдберриз|ozon|озон)\b", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"\b(\u043d\u0430\u0439\u0434\u0438|\u043f\u043e\u0438\u0449\u0438|\u043f\u043e\u0434\u0431\u0435\u0440\u0438|\u043f\u043e\u043a\u0430\u0436\u0438|\u043c\u043d\u0435|\u043d\u0443\u0436\u043d\u0430|\u043d\u0443\u0436\u0435\u043d|\u043d\u0443\u0436\u043d\u043e|\u043a\u0443\u043f\u0438\u0442\u044c|\u043d\u0430|\u0432)\b", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"\b(wildberries|\u0432\u0431|\u0432\u0430\u0439\u043b\u0434\u0431\u0435\u0440\u0440\u0438\u0437|ozon|\u043e\u0437\u043e\u043d)\b", " ", value, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", value).strip(" ,.!?()")


def marketplace_search_links(query: str) -> list[dict[str, str]]:
    q = clean_product_query(query)
    if not q:
        return []
    encoded = quote_plus(q)
    return [
        {"name": "Wildberries", "url": f"https://www.wildberries.ru/catalog/0/search.aspx?search={encoded}"},
        {"name": "Ozon", "url": f"https://www.ozon.ru/search/?text={encoded}"},
    ]


def format_marketplace_links(query: str) -> str:
    links = marketplace_search_links(query)
    return "\n".join(f"{item['name']}: {item['url']}" for item in links)
