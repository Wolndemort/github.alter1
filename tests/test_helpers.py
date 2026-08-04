from utils.helpers import deep_merge


def test_deep_merge_preserves_nested_memory():
    base = {"interests": {"music": ["rock"], "books": ["Dune"]}, "name": "Adam"}
    result = deep_merge(base, {"interests": {"food": ["pizza"]}})

    assert result == {
        "interests": {"music": ["rock"], "books": ["Dune"], "food": ["pizza"]},
        "name": "Adam",
    }


def test_deep_merge_replaces_scalar_value():
    assert deep_merge({"goals": {"current": "old"}}, {"goals": {"current": "new"}})["goals"]["current"] == "new"
