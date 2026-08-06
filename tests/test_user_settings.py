from datetime import datetime
from types import SimpleNamespace

from utils.user_settings import is_quiet_time, quiet_hours, user_setting


def test_user_setting_uses_default_and_custom_value():
    user = SimpleNamespace(tech_stack={"voice_replies": True})
    assert user_setting(user, "missing", False) is False
    assert user_setting(user, "voice_replies", False) is True


def test_quiet_hours_normalizes_values_and_bad_input():
    assert quiet_hours(SimpleNamespace(tech_stack={"quiet_start": 25, "quiet_end": -1})) == (1, 23)
    assert quiet_hours(SimpleNamespace(tech_stack={"quiet_start": "bad"})) == (23, 8)


def test_quiet_time_handles_wraparound_daytime_and_equal_bounds():
    wrapped = SimpleNamespace(tech_stack={"quiet_start": 23, "quiet_end": 8})
    daytime = SimpleNamespace(tech_stack={"quiet_start": 8, "quiet_end": 23})
    equal = SimpleNamespace(tech_stack={"quiet_start": 8, "quiet_end": 8})
    assert is_quiet_time(wrapped, datetime(2026, 1, 1, 23))
    assert is_quiet_time(wrapped, datetime(2026, 1, 1, 7))
    assert not is_quiet_time(wrapped, datetime(2026, 1, 1, 12))
    assert is_quiet_time(daytime, datetime(2026, 1, 1, 12))
    assert not is_quiet_time(equal, datetime(2026, 1, 1, 12))
