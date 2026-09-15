"""User-local date/time context for model prompts."""
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIMEZONE = "Europe/Moscow"

def current_time_context(location: dict | None = None, settings: dict | None = None) -> dict[str, str]:
    location = location if isinstance(location, dict) else {}
    settings = settings if isinstance(settings, dict) else {}
    name = str(location.get("timezone") or settings.get("timezone") or DEFAULT_TIMEZONE)
    try:
        zone = ZoneInfo(name)
    except ZoneInfoNotFoundError:
        name, zone = DEFAULT_TIMEZONE, ZoneInfo(DEFAULT_TIMEZONE)
    now = datetime.now(zone)
    return {"timezone": name, "date": now.strftime("%d.%m.%Y"), "time": now.strftime("%H:%M"), "iso": now.isoformat(timespec="seconds")}
