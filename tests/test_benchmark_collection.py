from utils.benchmark import parse_sse_stream


def test_sse_parser_collects_statuses_and_deltas_without_raw_payloads():
    body = (
        'data: {"type":"status","status":"analyzing"}\n\n'
        'data: {"type":"delta","text":"Привет"}\n\n'
        'data: {"type":"delta","text":"!"}\n\n'
        'data: {"type":"done"}\n\n'
    )
    answer, statuses, error = parse_sse_stream(body)
    assert answer == "Привет!"
    assert statuses == ["analyzing"]
    assert error is None
