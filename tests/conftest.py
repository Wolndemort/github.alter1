import pytest

from utils import ap_logic


@pytest.fixture(autouse=True)
def isolate_runtime_routing_flags(monkeypatch):
    """Keep route-policy tests deterministic when a real .env is present."""
    monkeypatch.setattr(ap_logic.config, "OPENROUTER_PAID_FIRST", False)
