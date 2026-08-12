from scripts.collect_capability_smoke import READ_ONLY_CHECKS, classify_status


def test_capability_smoke_is_read_only_and_does_not_include_paid_jobs():
    paths = [path for _, path, _ in READ_ONLY_CHECKS]
    assert all(path.startswith("/api/v1/") for path in paths)
    assert not any("media/jobs" in path or "generate" in path for path in paths)
    assert len(paths) == len(set(paths))


def test_capability_smoke_marks_tolerated_provider_outage_as_degraded():
    assert classify_status(200, (200, 502, 503)) == (True, False, None)
    assert classify_status(502, (200, 502, 503)) == (True, True, "optional_provider_unavailable")
    assert classify_status(500, (200, 502, 503)) == (False, False, "unexpected_http_500")
