"""Cheap, deterministic request routing for the low-latency chat path."""

from dataclasses import dataclass

from utils.intent import conversation_mode, is_web_request, is_youtube_request


@dataclass(frozen=True)
class RequestRoute:
    kind: str
    initial_status: str
    streamable: bool


def classify_request(text: str) -> RequestRoute:
    value = (text or "").strip()
    mode = conversation_mode(value)
    if is_youtube_request(value):
        return RequestRoute("youtube", "searching", False)
    if mode == "planning":
        return RequestRoute("planning", "planning", True)
    if mode == "decision":
        return RequestRoute("decision", "analyzing", True)
    if is_web_request(value):
        return RequestRoute("web", "searching", False)
    return RequestRoute("chat", "analyzing", True)
