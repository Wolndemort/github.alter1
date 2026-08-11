from utils import metrics


def test_latency_snapshot_reports_percentiles_and_is_resettable():
    metrics.reset()
    for value in (10, 20, 30, 100):
        metrics.observe("first_token", value)
    snapshot = metrics.latency_snapshot()["first_token"]
    assert snapshot["count"] == 4
    assert snapshot["p50_ms"] == 20
    assert snapshot["p95_ms"] == 30
    metrics.reset()
    assert metrics.latency_snapshot() == {}
