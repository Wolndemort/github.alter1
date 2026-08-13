import pytest

from services.document_ingestion import edit_document


def test_document_edit_rejects_missing_source_text():
    with pytest.raises(ValueError, match="не нашёл"):
        edit_document("notes.txt", b"actual text", "missing => new")


def test_document_edit_matches_case_and_line_breaks():
    result = edit_document("notes.txt", "Статус:\nСТАРЫЙ   текст".encode(), "старый текст => новый статус")
    assert result.data == "Статус:\nновый статус".encode()
