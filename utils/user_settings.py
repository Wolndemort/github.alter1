from datetime import datetime


DEFAULT_CHECKIN_INTERVAL_HOURS = 24
DEFAULT_HEALTH_FOLLOWUP_HOURS = 4


def user_setting(user, key: str, default):
    return (user.tech_stack or {}).get(key, default)


def quiet_hours(user) -> tuple[int, int]:
    settings = user.tech_stack or {}
    try:
        start = int(settings.get("quiet_start", 23)) % 24
        end = int(settings.get("quiet_end", 8)) % 24
        return start, end
    except (TypeError, ValueError):
        return 23, 8


def is_quiet_time(user, current: datetime) -> bool:
    start, end = quiet_hours(user)
    if start == end:
        return False
    if start < end:
        return start <= current.hour < end
    return current.hour >= start or current.hour < end
