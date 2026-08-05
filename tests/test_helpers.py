from utils.helpers import deep_merge
from utils.helpers import merge_memory


def test_deep_merge_preserves_nested_memory():
    base = {"interests": {"music": ["rock"], "books": ["Dune"]}, "name": "Adam"}
    result = deep_merge(base, {"interests": {"food": ["pizza"]}})

    assert result == {
        "interests": {"music": ["rock"], "books": ["Dune"], "food": ["pizza"]},
        "name": "Adam",
    }


def test_deep_merge_replaces_scalar_value():
    assert deep_merge({"goals": {"current": "old"}}, {"goals": {"current": "new"}})["goals"]["current"] == "new"


def test_merge_memory_preserves_and_deduplicates_fact_lists():
    result = merge_memory(
        {"preferences": {"colors": ["чёрный", "серый"]}},
        {"preferences": {"colors": ["серый", "синий"]}},
    )
    assert result["preferences"]["colors"] == ["чёрный", "серый", "синий"]
