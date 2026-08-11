from utils import ap_logic


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
