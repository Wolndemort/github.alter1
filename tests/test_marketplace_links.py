from utils.marketplace_links import marketplace_search_links, clean_product_query


def test_marketplace_query_removes_conversation_words():
    assert clean_product_query("найди мне рубашку в полосу на вб") == "рубашку полосу"


def test_marketplace_links_are_search_urls_and_encode_query():
    links = marketplace_search_links("корм для кота")
    assert len(links) == 2
    assert "wildberries.ru/catalog/0/search.aspx?search=" in links[0]["url"]
    assert "ozon.ru/search/?text=" in links[1]["url"]
    assert "%D0%BA%D0%BE%D1%80%D0%BC" in links[0]["url"]
