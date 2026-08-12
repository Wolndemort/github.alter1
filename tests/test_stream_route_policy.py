import pytest

from utils import ap_logic


@pytest.fixture(autouse=True)
def isolated_model_config(monkeypatch):
    values = {
        "OPENROUTER_FREE_MODEL": "nvidia/nemotron-3-super-120b-a12b:free",
        "OPENROUTER_FREE_MODEL_2": "openai/gpt-oss-20b:free",
        "OPENROUTER_FREE_MODELS_ENABLED": True,
        "OPENROUTER_PAID_FIRST": False,
    }
    for key, value in values.items(): monkeypatch.setattr(ap_logic.config, key, value)


def test_short_stream_uses_responsive_model_before_heavy_model():
    route = ap_logic._stream_model_route([{"role": "user", "content": "Привет"}])
    assert route[0] == ap_logic.config.OPENROUTER_FREE_MODEL_2
    assert len(route) <= ap_logic.config.AI_STREAM_MAX_MODELS


def test_short_stream_has_paid_fallback_after_free_attempt():
    route = ap_logic._stream_model_route([{"role": "user", "content": "Привет"}])
    if ap_logic.config.OPENROUTER_ALLOW_PAID_FALLBACK:
        assert ap_logic.config.OPENROUTER_MODEL in route


def test_complex_stream_keeps_primary_model_first():
    route = ap_logic._stream_model_route([{"role": "user", "content": "составь подробный план миграции базы данных"}])
    assert route[0] == ap_logic.config.OPENROUTER_FREE_MODEL


def test_paid_first_mode_prioritizes_reliable_model_and_keeps_free_fallback(monkeypatch):
    monkeypatch.setattr(ap_logic.config, "OPENROUTER_PAID_FIRST", True)
    monkeypatch.setattr(ap_logic.config, "OPENROUTER_ALLOW_PAID_FALLBACK", True)
    monkeypatch.setattr(ap_logic.config, "AI_STREAM_MAX_MODELS", 3)
    ap_logic._MODEL_COOLDOWN_UNTIL.clear()
    route = ap_logic._stream_model_route([{"role": "user", "content": "Привет"}])
    assert route[0] == ap_logic.config.OPENROUTER_MODEL
    assert ap_logic.config.OPENROUTER_FREE_MODEL_2 in route


def test_free_pool_can_be_disabled_for_production(monkeypatch):
    monkeypatch.setattr(ap_logic.config, "OPENROUTER_FREE_MODELS_ENABLED", False)
    monkeypatch.setattr(ap_logic.config, "OPENROUTER_PAID_FIRST", True)
    monkeypatch.setattr(ap_logic.config, "OPENROUTER_ALLOW_PAID_FALLBACK", True)
    route = ap_logic._stream_model_route([{"role": "user", "content": "Привет"}])
    assert route[0] == ap_logic.config.OPENROUTER_MODEL
    assert all(":free" not in model for model in route)
