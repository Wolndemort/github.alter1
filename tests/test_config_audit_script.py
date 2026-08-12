from pathlib import Path


def test_config_audit_script_exists_and_is_non_secret():
    source = (Path(__file__).parents[1] / "scripts" / "config-audit.py").read_text(encoding="utf-8")
    assert "configuration_snapshot" in source
    assert "get_secret_value" not in source
