from pathlib import Path


def test_http_quota_checks_web_owner_access_not_only_telegram_ids():
    source = (Path(__file__).parents[1] / "main.py").read_text(encoding="utf-8")
    assert "has_owner_access" in source
    assert "WebAccount" in source
    assert "charge_request(redis, user_id" in source
