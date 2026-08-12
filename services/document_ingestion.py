"""Safe text extraction for documents used by chat and durable agents."""
from __future__ import annotations

import io
import json
import re
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path

from utils.agent_engine import start_agent
from utils.external_content import audit_external_content


MAX_DOCUMENT_BYTES = 25 * 1024 * 1024
MAX_DOCUMENT_CHARS = 120_000
SUPPORTED_EXTENSIONS = {".txt", ".md", ".markdown", ".json", ".csv", ".pdf", ".docx"}
EDITABLE_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".json", ".docx"}
OCR_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".tiff", ".bmp"}


@dataclass(frozen=True)
class Document:
    filename: str
    media_type: str
    text: str
    pages: int | None = None
    ocr_used: bool = False

    @property
    def chars(self) -> int:
        return len(self.text)


@dataclass(frozen=True)
class EditedDocument:
    """A bounded, exportable document result produced by an explicit edit."""
    filename: str
    media_type: str
    data: bytes


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


def document_profile(document: Document) -> dict:
    """Return bounded, deterministic signals for agents and audit UIs."""
    lines = [line.strip() for line in document.text.splitlines() if line.strip()]
    tables = [line for line in lines if line.count("|") >= 2 or "\t" in line]
    dates = sorted(set(re.findall(r"\b(?:\d{1,2}[./]){2}\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b", document.text)))
    amounts = sorted(set(re.findall(r"(?:\d[\d ]{0,12} ?(?:₽|руб\.?|\$|€|USD|EUR))", document.text, re.IGNORECASE)))
    return {
        "filename": document.filename,
        "media_type": document.media_type,
        "pages": document.pages,
        "chars": document.chars,
        "lines": len(lines),
        "tables": tables[:100],
        "dates": dates[:100],
        "amounts": amounts[:100],
        "ocr_used": document.ocr_used,
        "needs_ocr": document.pages is not None and not document.text,
    }


def ocr_image_text(filename: str, data: bytes, *, language: str = "rus+eng") -> Document:
    """Run bounded local OCR when Pillow/Tesseract are installed.

    OCR is deliberately optional: hosted vision remains the fallback when a
    deployment does not have the native Tesseract binary.
    """
    if not data:
        raise ValueError("image is empty")
    if len(data) > MAX_DOCUMENT_BYTES:
        raise ValueError("image is too large")
    if _extension(filename) not in OCR_EXTENSIONS:
        raise ValueError("unsupported OCR image type")
    try:
        from PIL import Image
        import pytesseract
        image = Image.open(io.BytesIO(bytes(data)))
        text = pytesseract.image_to_string(image, lang=language)
    except ImportError as exc:
        raise ValueError("local OCR is unavailable; use vision analysis") from exc
    except Exception as exc:
        raise ValueError("could not OCR image") from exc
    return Document(Path(filename).name[:180], "text/plain", _clean(text), ocr_used=True)


def edit_document(filename: str, data: bytes, instruction: str, media_type: str = "") -> EditedDocument:
    """Apply only deterministic replacements supplied as ``old => new`` lines.

    AI-generated edits must be converted to this explicit format by the caller;
    this keeps exports auditable and prevents accidental destructive rewrites.
    """
    extension = _extension(filename)
    if extension not in EDITABLE_EXTENSIONS:
        raise ValueError("this document format requires layout-aware editing")
    document = extract_document(filename, data, media_type)
    replacements = []
    for line in (instruction or "").splitlines():
        if "=>" in line:
            old, new = line.split("=>", 1)
            if old.strip():
                replacements.append((old.strip(), new.strip()))
    if not replacements:
        raise ValueError("provide explicit replacements in the form: old => new")
    text = document.text
    for old, new in replacements:
        text = text.replace(old, new)
    if extension == ".json":
        try:
            output = json.dumps(json.loads(text), ensure_ascii=False, indent=2).encode("utf-8")
        except json.JSONDecodeError as exc:
            raise ValueError("edit would produce invalid JSON") from exc
    elif extension == ".docx":
        try:
            from docx import Document as DocxDocument
            source = DocxDocument(io.BytesIO(bytes(data)))
            for paragraph in source.paragraphs:
                for old, new in replacements:
                    for run in paragraph.runs:
                        run.text = run.text.replace(old, new)
            output_buffer = io.BytesIO()
            source.save(output_buffer)
            output = output_buffer.getvalue()
        except ImportError as exc:
            raise ValueError("DOCX support is not installed") from exc
    else:
        output = text.encode("utf-8")
    return EditedDocument(document.filename, document.media_type, output)


def start_document_agent(settings: dict | None, document: Document, goal: str, *, horizon_minutes: int = 60) -> dict:
    """Create a durable document agent without storing unbounded raw input."""
    bounded_text = document.text[:30000]
    tasks = [
        {"id": "document_scope", "title": "Определить цель и структуру документа", "priority": 1},
        {"id": "document_facts", "title": "Извлечь ключевые факты, даты, числа и ограничения", "depends_on": ["document_scope"]},
        {"id": "document_actions", "title": "Сформировать практические выводы и задачи", "depends_on": ["document_facts"]},
        {"id": "document_verify", "title": "Проверить выводы и подготовить результат", "depends_on": ["document_actions"]},
    ]
    return start_agent(
        settings, goal or f"Работа с документом {document.filename}", horizon_minutes=horizon_minutes,
        tasks=tasks, constraints={"document_context": bounded_text, "document_filename": document.filename, "document_profile": document_profile(document), "external_content_audit": audit_external_content(bounded_text)},
    )
