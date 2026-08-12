import pytest

from utils import ap_logic


@pytest.fixture(autouse=True)
def isolate_runtime_routing_flags(monkeypatch):
    """Keep route-policy tests deterministic when a real .env is present."""
    monkeypatch.setattr(ap_logic.config, "OPENROUTER_PAID_FIRST", False)
    monkeypatch.setattr(ap_logic.config, "OPENROUTER_FREE_MODELS_ENABLED", True)
    monkeypatch.setattr(ap_logic.config, "OPENROUTER_ALLOW_PAID_FALLBACK", False)
    monkeypatch.setattr(ap_logic.config, "OPENROUTER_FREE_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
    monkeypatch.setattr(ap_logic.config, "OPENROUTER_FREE_MODEL_2", "openai/gpt-oss-20b:free")
    monkeypatch.setattr(ap_logic.config, "OPENROUTER_FREE_MODEL_3", "google/gemma-4-31b-it:free")
    monkeypatch.setattr(ap_logic.config, "OPENROUTER_FREE_MODEL_4", "inclusionai/ling-3.0-tiny:free")
    monkeypatch.setattr(ap_logic.config, "OPENROUTER_FREE_MODEL_5", "nvidia/nemotron-3-nano-30b-a3b:free")
    ap_logic._MODEL_COOLDOWN_UNTIL.clear()
