from pathlib import Path

from scripts.collect_capability_stateful_smoke import check


def test_stateful_smoke_does_not_call_paid_media_generation():
    source = (Path(__file__).parents[1] / "scripts" / "collect_capability_stateful_smoke.py").read_text(encoding="utf-8")
    assert "/api/v1/media/generate" not in source
    assert "/api/v1/media/jobs" not in source


def test_check_marks_expected_status_as_success():
    class Response:
        status_code = 200
        def json(self):
            return {"ok": True}

    class Client:
        def request(self, *args, **kwargs):
            return Response()

    record = check(Client(), "https://example.test", {}, "case", "GET", "/api/v1/account", (200,))
    assert record["ok"] is True
    assert record["body"] == {"ok": True}
