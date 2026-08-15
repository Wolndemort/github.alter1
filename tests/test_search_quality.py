from utils.web_search import _annotate_results, _canonical_url, _page_text, _rank_results


def test_search_canonicalization_removes_tracking_and_trailing_slash():
    assert _canonical_url("HTTPS://Example.com/path/?utm_source=x") == "https://example.com/path"


def test_search_quality_prioritizes_official_sources_and_adds_evidence_metadata():
    items = [
        {"title": "Blog", "url": "https://blog.example/path", "content": "x"},
        {"title": "Official", "url": "https://agency.gov/info", "content": "y"},
    ]
    ranked = _rank_results(items, 2)
    annotated = _annotate_results(ranked)
    assert annotated[0]["title"] == "Official"
    assert annotated[0]["source_quality"] == "official"
    assert annotated[1]["source_domain"] == "blog.example"


def test_page_text_removes_scripts_and_normalizes_html():
    body = b"<html><script>secret()</script><main>Hello <b>world</b>.</main></html>"
    assert _page_text(body) == "Hello world ."
