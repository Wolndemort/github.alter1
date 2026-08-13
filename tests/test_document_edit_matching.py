import pytest

from services.document_ingestion import edit_document


def test_document_edit_rejects_missing_source_text():
    with pytest.raises(ValueError, match="не нашёл"):
        edit_document("notes.txt", b"actual text", "missing => new")
