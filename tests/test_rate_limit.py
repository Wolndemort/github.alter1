from utils.rate_limit import DailyRequestLimit


def test_daily_request_limit_blocks_after_limit():
    limiter = DailyRequestLimit(limit=2)
    assert limiter.allow(7)
    assert limiter.allow(7)
    assert not limiter.allow(7)


def test_daily_request_limit_is_per_user():
    limiter = DailyRequestLimit(limit=1)
    assert limiter.allow(1)
    assert limiter.allow(2)
