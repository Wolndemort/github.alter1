from services.attachment_pipeline import attachment_kind, prepare_attachment


def test_attachment_kind_covers_all_media_families():
    assert attachment_kind("contract.pdf") == "document"
    assert attachment_kind("photo.jpg") == "image"
    assert attachment_kind("clip.mp4") == "video"
    assert attachment_kind("song.mp3") == "audio"


def test_document_attachment_has_bounded_agent_context_and_profile():
    context = prepare_attachment("notes.txt", "Дата: 2026-08-12\nA | B | C".encode())
    assert context.kind == "document"
    assert context.document is not None
    assert context.profile["dates"] == ["2026-08-12"]
    assert "A | B | C" in context.agent_context


def test_image_falls_back_to_vision_without_local_ocr():
    context = prepare_attachment("photo.jpg", b"image", use_local_ocr=False)
    assert context.kind == "image"
    assert context.needs_vision is True
    assert context.document is None
