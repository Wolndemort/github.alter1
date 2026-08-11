from scripts.collect_capability_smoke import READ_ONLY_CHECKS


def test_capability_smoke_is_read_only_and_does_not_include_paid_jobs():
    paths = [path for _, path, _ in READ_ONLY_CHECKS]
    assert all(path.startswith("/api/v1/") for path in paths)
    assert not any("media/jobs" in path or "generate" in path for path in paths)
    assert len(paths) == len(set(paths))
