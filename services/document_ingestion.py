"""Safe text extraction for documents used by chat and durable agents."""
from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass
from pathlib import Path


MAX_DOCUMENT_BYTES = 25 * 1024 * 1024
MAX_DOCUMENT_CHARS = 120_000
SUPPORTED_EXTENSIONS = {".txt", ".md", ".markdown", ".json", ".csv", ".pdf", ".docx"}


@dataclass(frozen=True)
class Document:
    filename: str
    media_type: str
    text: str
    pages: int | None = None

    @property
    def chars(self) -> int:
        return len(self.text)


def _clean(text: str) -> str:
    value = text.replace("\x00", "")
    value = re.sub(r"\n{3,}", "\n\n", value)
    value = re.sub(r"[ \t]+", " ", value)
    return value.strip()[:MAX_DOCUMENT_CHARS]


def _extension(filename: str) -> str:
    return Path(filename or "document").suffix.casefold()


def extract_document(filename: str, data: bytes, media_type: str = "") -> Document:
    """Extract bounded text, raising a user-safe ValueError for unsupported input."""
    if not isinstance(data, (bytes, bytearray)) or not data:
        raise ValueError("document is empty")
    if len(data) > MAX_DOCUMENT_BYTES:
        raise ValueError("document is too large")
    filename = Path(filename or "document").name[:180]
    extension = _extension(filename)
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError("unsupported document type")
    if extension in {".txt", ".md", ".markdown", ".csv"}:
        text = bytes(data).decode("utf-8-sig", errors="replace")
        return Document(filename, media_type or "text/plain", _clean(text))
    if extension == ".json":
        try:
            value = json.loads(bytes(data).decode("utf-8-sig"))
            text = json.dumps(value, ensure_ascii=False, indent=2)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid JSON document") from exc
        return Document(filename, media_type or "application/json", _clean(text))
    if extension == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(bytes(data)))
            text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
            return Document(filename, media_type or "application/pdf", _clean(text), pages=len(reader.pages))
        except ImportError as exc:
            raise ValueError("PDF support is not installed") from exc
        except Exception as exc:
            raise ValueError("could not read PDF document") from exc
    try:
        from docx import Document as DocxDocument
        document = DocxDocument(io.BytesIO(bytes(data)))
        parts = [paragraph.text for paragraph in document.paragraphs]
        for table in document.tables:
            parts.extend(" | ".join(cell.text for cell in row.cells) for row in table.rows)
        return Document(filename, media_type or "application/vnd.openxmlformats-officedocument.wordprocessingml.document", _clean("\n".join(parts)))
    except ImportError as exc:
        raise ValueError("DOCX support is not installed") from exc
    except Exception as exc:
        raise ValueError("could not read DOCX document") from exc


def document_chunks(document: Document, chunk_chars: int = 6000) -> list[str]:
    size = max(500, min(int(chunk_chars), 12000))
    return [document.text[index:index + size] for index in range(0, len(document.text), size)] or [""]
