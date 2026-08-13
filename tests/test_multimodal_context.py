import json

from utils.multimodal_context import attachment_context_message


def test_attachment_context_is_bounded_structured_and_does_not_store_binary_data():
    message = attachment_context_message(
        kind="video", filename="clip.mp4", media_type="video/mp4",
        transcript="speech", observation="frames show a product",
        profile={"duration_seconds": 12}, operation="analysis",
        artifact_filename="alter-result.mp4", artifact_media_type="video/mp4",
    )
    assert len(message) <= 7100
    payload = json.loads(message.splitlines()[1])
    assert payload["kind"] == "video"
    assert payload["transcript"] == "speech"
    assert "binary" not in message
    assert "alter-result.mp4" in message


def test_attachment_context_truncates_untrusted_derived_text():
    message = attachment_context_message(kind="audio", filename="voice.m4a", transcript="x" * 20000)
    assert len(message) <= 7100
    assert "<untrusted_attachment_context>" in message
