from types import SimpleNamespace

from utils.config_audit import configuration_snapshot


def test_configuration_snapshot_contains_only_non_secret_state():
    settings = SimpleNamespace(
        OPENROUTER_MODEL="primary", OPENROUTER_FREE_MODEL="free", OPENROUTER_FREE_MODEL_2=None,
        OPENROUTER_FREE_MODEL_3=None, OPENROUTER_FREE_MODEL_4=None, OPENROUTER_FREE_MODEL_5=None,
        OPENROUTER_PAID_FIRST=False, OPENROUTER_ALLOW_PAID_FALLBACK=False,
        YANDEX_MAPS_GEOCODER_API_KEY="secret", YANDEX_MAPS_ORG_API_KEY=None,
        YANDEX_MAPS_ROUTE_API_KEY=None, YANDEX_MAPS_DISTANCE_MATRIX_API_KEY=None,
        OPENROUTER_API_KEY="secret", YANDEX_SEARCH_API_KEY=None, FIRECRAWL_API_KEY=None,
    )
    result = configuration_snapshot(settings)
    assert result["maps"] == {"geocoder": True, "organizations": False, "route": False, "distance_matrix": False}
    assert "secret" not in str(result)


def test_configuration_snapshot_warns_about_inconsistent_paid_mode():
    settings = SimpleNamespace(OPENROUTER_MODEL="primary", OPENROUTER_FREE_MODEL=None, OPENROUTER_FREE_MODEL_2=None, OPENROUTER_FREE_MODEL_3=None, OPENROUTER_FREE_MODEL_4=None, OPENROUTER_FREE_MODEL_5=None, OPENROUTER_PAID_FIRST=True, OPENROUTER_ALLOW_PAID_FALLBACK=False, YANDEX_MAPS_GEOCODER_API_KEY=None)
    result = configuration_snapshot(settings)
    assert "no_free_models_configured" in result["warnings"]
    assert "paid_first_without_paid_fallback" in result["warnings"]
