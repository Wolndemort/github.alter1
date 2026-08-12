from utils import metrics


def test_latency_snapshot_exposes_p99():
    metrics.reset()
    for value in range(1, 101):
        metrics.observe("test", value)
    result = metrics.latency_snapshot()["test"]
    assert "p50_ms" in result and "p95_ms" in result and "p99_ms" in result
    assert result["p99_ms"] >= result["p95_ms"]
