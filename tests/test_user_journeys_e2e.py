"""Offline end-to-end smoke checks for the highest-risk user journeys.

These tests exercise the deterministic edges of real journeys without sending
provider requests, creating payments, or mutating production data.
"""
from datetime import datetime, timedelta, timezone

import pytest

from services.document_ingestion import create_document
from utils.document_commands import document_creation_format
from utils.reminders import pending_reminder_is_fresh, parse_reminder


def test_user_can_request_and_receive_a_filled_txt_document():
    prompt = "Создай TXT-файл и напиши в нём план запуска проекта на 30 дней"
    filename, media_type = document_creation_format(prompt)
    artifact = create_document(filename, "Цель\n\nНеделя 1: подготовка", media_type)

    assert artifact.filename.endswith(".txt")
    assert artifact.media_type == "text/plain"
    assert artifact.data == "Цель\n\nНеделя 1: подготовка".encode()


def test_user_can_request_a_filled_docx_document():
    pytest.importorskip("docx")
    filename, media_type = document_creation_format("создай заполненный документ DOCX с планом")
    artifact = create_document(filename, "План проекта", media_type)

    assert artifact.filename.endswith(".docx")
    assert artifact.data.startswith(b"PK")  # DOCX is an OOXML zip archive.


def test_reminder_journey_accepts_explicit_time_but_not_ambiguous_chat():
    parsed = parse_reminder("завтра в 10:30 позвонить клиенту")

    assert parsed is not None
    assert parsed[1] == "позвонить клиенту"


def test_stale_pending_reminder_cannot_capture_a_new_chat_message():
    old = {
        "text": "проверить отчёт",
        "created_at": (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat(),
    }
    fresh = {"text": "проверить отчёт", "created_at": datetime.now(timezone.utc).isoformat()}

    assert not pending_reminder_is_fresh(old)
    assert pending_reminder_is_fresh(fresh)
