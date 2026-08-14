"""Non-secret runtime configuration audit used by diagnostics and CI."""
from __future__ import annotations


def configuration_snapshot(settings) -> dict:
    def present(name: str) -> bool:
        value = getattr(settings, name, None)
        return bool(value)

    free_models = [getattr(settings, name, None) for name in (
        "OPENROUTER_FREE_MODEL", "OPENROUTER_FREE_MODEL_2", "OPENROUTER_FREE_MODEL_3",
        "OPENROUTER_FREE_MODEL_4", "OPENROUTER_FREE_MODEL_5",
    )]
    return {
        "models": {
            "primary": getattr(settings, "OPENROUTER_MODEL", None),
            "free": [str(model) for model in free_models if model],
            "paid_first": bool(getattr(settings, "OPENROUTER_PAID_FIRST", False)),
            "paid_fallback": bool(getattr(settings, "OPENROUTER_ALLOW_PAID_FALLBACK", False)),
        },
        "maps": {
            "geocoder": present("YANDEX_MAPS_GEOCODER_API_KEY"),
            "organizations": present("YANDEX_MAPS_ORG_API_KEY"),
            "route": present("YANDEX_MAPS_ROUTE_API_KEY"),
            "distance_matrix": present("YANDEX_MAPS_DISTANCE_MATRIX_API_KEY"),
        },
        "providers": {
            "openrouter": present("OPENROUTER_API_KEY"),
            "yandex_search": present("YANDEX_SEARCH_API_KEY"),
            "firecrawl": present("FIRECRAWL_API_KEY"),
            "tavily": present("TAVILY_API_KEY"),
            "google_search": present("GOOGLE_CSE_API_KEY") and present("GOOGLE_CSE_ID"),
            "serper": present("SERPER_API_KEY"),
            "2gis": present("TWOGIS_API_KEY"),
            "youtube": present("YOUTUBE_API_KEY"),
            "elevenlabs": present("ELEVENLABS_API_KEY"),
            "fal": present("MEDIA_GENERATION_API_KEY"),
            "google_calendar": present("GOOGLE_CLIENT_ID") and present("GOOGLE_CLIENT_SECRET"),
        },
        "warnings": _warnings(settings, free_models),
    }


def _warnings(settings, free_models: list) -> list[str]:
    warnings = []
    if not any(free_models):
        warnings.append("no_free_models_configured")
    if bool(getattr(settings, "OPENROUTER_PAID_FIRST", False)) and not bool(getattr(settings, "OPENROUTER_ALLOW_PAID_FALLBACK", False)):
        warnings.append("paid_first_without_paid_fallback")
    if not getattr(settings, "YANDEX_MAPS_GEOCODER_API_KEY", None):
        warnings.append("yandex_geocoder_unconfigured")
    return warnings
