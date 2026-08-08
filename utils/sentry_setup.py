"""Optional Sentry error monitoring with sensitive request data removed."""
from __future__ import annotations

import os


def _scrub_event(event: dict, hint: dict) -> dict:
    request = event.get("request")
    if isinstance(request, dict):
        if request.get("url"):
            request["url"] = str(request["url"]).split("?", 1)[0]
        request.pop("query_string", None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            for name in list(headers):
                if str(name).lower() in {"authorization", "cookie", "x-api-key"}:
                    headers[name] = "[Filtered]"
    return event


def init_sentry() -> None:
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        return
    try:
        import sentry_sdk
    except ImportError:
        return
    sentry_sdk.init(
        dsn=dsn,
        environment=os.getenv("SENTRY_ENVIRONMENT", "production"),
        release=os.getenv("SENTRY_RELEASE") or None,
        send_default_pii=False,
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.0")),
        before_send=_scrub_event,
    )
