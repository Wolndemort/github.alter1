from types import SimpleNamespace

from utils.action_log import MAX_ACTIONS, append_action, read_actions


def test_action_log_contains_metadata_only_and_is_bounded():
    user = SimpleNamespace(tech_stack={})
    for index in range(MAX_ACTIONS + 5):
        append_action(user, "chat", "ok", route="fast", prompt="must not be stored", count=index)
    entries = read_actions(user)
    assert len(entries) == MAX_ACTIONS
    assert "prompt" not in entries[-1]
    assert entries[-1]["count"] == str(MAX_ACTIONS + 4)


def test_private_mode_does_not_write_action_log():
    user = SimpleNamespace(tech_stack={"private_mode": True})
    append_action(user, "chat", "ok", route="fast")
    assert read_actions(user) == []


def test_billing_metadata_is_safe_and_visible():
    user = SimpleNamespace(tech_stack={})
    append_action(user, "billing", "reserved", credits=100, provider="fal", secret="must not store")
    entry = read_actions(user)[0]
    assert entry["credits"] == "100"
    assert entry["provider"] == "fal"
    assert "secret" not in entry
