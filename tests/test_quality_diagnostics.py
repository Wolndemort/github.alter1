from utils import metrics


def test_quality_diagnostics_inputs_are_available_for_dashboard():
    metrics.reset()
    metrics.increment("ai.tool.ok", tool="web_search")
    metrics.increment("ai.tool.failure", tool="get_weather")
    snapshot = metrics.snapshot()
    assert snapshot["ai.tool.ok"] == 1
    assert snapshot["ai.tool.failure"] == 1
