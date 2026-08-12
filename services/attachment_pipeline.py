"""Format-agnostic attachment preparation for chat and durable agents."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from services.document_ingestion import Document, document_profile, extract_document, ocr_image_text


@dataclass(frozen=True)
class AttachmentContext:
    filename: str
    kind: str
    media_type: str
    document: Document | None
    profile: dict
    agent_context: str
    needs_vision: bool = False


def attachment_kind(filename: str, media_type: str = "") -> str:
    mime = (media_type or "").casefold()
    if mime.startswith("image/") or Path(filename).suffix.casefold() in {".png", ".jpg", ".jpeg", ".webp", ".tiff", ".bmp"}:
        return "image"
    if mime.startswith("video/") or Path(filename).suffix.casefold() in {".mp4", ".mov", ".mkv", ".webm"}:
        return "video"
    if mime.startswith("audio/") or Path(filename).suffix.casefold() in {".mp3", ".wav", ".m4a", ".ogg", ".flac"}:
        return "audio"
    return "document"


def prepare_attachment(filename: str, data: bytes, media_type: str = "", *, use_local_ocr: bool = True) -> AttachmentContext:
    """Prepare bounded context without calling paid providers."""
    kind = attachment_kind(filename, media_type)
    if kind == "document":
        document = extract_document(filename, data, media_type)
        profile = document_profile(document)
        return AttachmentContext(document.filename, kind, document.media_type, document, profile, document.text[:30000])
    if kind == "image" and use_local_ocr:
        try:
            document = ocr_image_text(filename, data)
            return AttachmentContext(filename, kind, media_type or "image/*", document, document_profile(document), document.text[:30000])
        except ValueError:
            pass
    return AttachmentContext(Path(filename or "attachment").name[:180], kind, media_type or "application/octet-stream", None, {"kind": kind}, "", needs_vision=kind in {"image", "video"})
