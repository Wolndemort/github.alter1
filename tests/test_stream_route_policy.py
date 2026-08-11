from utils import ap_logic


def test_short_stream_uses_responsive_model_before_heavy_model():
    route = ap_logic._stream_model_route([{"role": "user", "content": "Привет"}])
    assert route[0] == ap_logic.config.OPENROUTER_FREE_MODEL_2


def test_complex_stream_keeps_primary_model_first():
    route = ap_logic._stream_model_route([{"role": "user", "content": "составь подробный план миграции базы данных"}])
    assert route[0] == ap_logic.config.OPENROUTER_FREE_MODEL
