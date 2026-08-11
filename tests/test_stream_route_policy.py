from utils.request_routing import classify_request


def test_web_requests_keep_sse_transport_but_use_tool_aware_path():
    route = classify_request("Найди актуальную цену iPhone")
    assert route.initial_status == "searching"
    assert not route.streamable


def test_short_requests_keep_token_streaming_path():
    route = classify_request("Привет")
    assert route.streamable
