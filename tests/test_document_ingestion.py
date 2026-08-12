import json

import pytest

from services.document_ingestion import MAX_DOCUMENT_BYTES, document_chunks, extract_document


def test_text_document_is_normalized_and_chunked():
    document = extract_document("notes.md", b"# Title\n\n\ntext", "text/markdown")
    assert document.filename == "notes.md"
    assert document.text == "# Title\n\ntext"
    assert document_chunks(document, 5) == [document.text]


def test_json_document_is_pretty_printed():
    document = extract_document("data.json", json.dumps({"name": "Alter"}).encode(), "application/json")
    assert '"name": "Alter"' in document.text


def test_document_rejects_unsupported_and_oversized_input():
    with pytest.raises(ValueError, match="unsupported"):
        extract_document("malware.exe", b"x")
    with pytest.raises(ValueError, match="too large"):
        extract_document("notes.txt", b"x" * (MAX_DOCUMENT_BYTES + 1))
