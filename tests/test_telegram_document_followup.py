import base64
from types import SimpleNamespace

import pytest

from handlers import user_handlers


@pytest.mark.asyncio
async def test_telegram_followup_edit_reuses_latest_document_artifact(monkeypatch):
    answers = []

    async def answer(text):
        answers.append(text)

    async def answer_document(*args, **kwargs):
        answers.append(kwargs.get("caption"))

    message = SimpleNamespace(
        text="замени draft на ready",
        answer=answer,
        answer_document=answer_document,
    )
    user = SimpleNamespace(id=7)
    edited = SimpleNamespace(data=b"ready", filename="status.txt", media_type="text/plain")
    recorded = {}

    async def latest_artifact(user_id, *, kind):
        assert (user_id, kind) == (7, "document")
        return {"filename": "status.txt", "media_type": "text/plain", "data_base64": base64.b64encode(b"draft").decode()}

    async def save_artifact(*args, **kwargs):
        return "edited-2"

    async def record_document_turn(*args, **kwargs):
        recorded.update(kwargs)
        return 19

    monkeypatch.setattr(user_handlers, "latest_artifact", latest_artifact)
    monkeypatch.setattr(user_handlers, "edit_document", lambda *args: edited)
    monkeypatch.setattr(user_handlers, "save_artifact", save_artifact)
    monkeypatch.setattr(user_handlers, "record_document_turn", record_document_turn)

    assert await user_handlers.edit_latest_telegram_document(message, user, object(), message.text)
    assert recorded["artifact_id"] == "edited-2"
    assert answers == ["Готово — отправляю последнюю изменённую версию документа."]
