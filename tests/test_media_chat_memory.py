import pytest

from data.models import Session, User
from services import media_chat_service


class Result:
    def scalar_one_or_none(self):
        return None


class Db:
    def __init__(self):
        self.user = User(id=7, first_name="Test", memory={}, tech_stack={})

    async def get(self, model, user_id):
        return self.user if user_id == 7 else None

    async def execute(self, statement):
        return Result()

    def add(self, value):
        if isinstance(value, Session):
            value.id = 11

    async def flush(self):
        pass

    async def commit(self):
        pass


@pytest.mark.asyncio
async def test_mobile_photo_turn_recalls_and_persists_memory(monkeypatch):
    recalled = []
    remembered = []

    async def fake_recall(db, user_id, text):
        recalled.append(text)
        return ["Ранее обсуждали чёрную куртку"]

    async def fake_remember(db, user_id, text, source="conversation"):
        remembered.append((user_id, text, source))

    async def vision(prompt, media, **kwargs):
        assert kwargs["memory"]["related_previous_context"] == ["Ранее обсуждали чёрную куртку"]
        return "Фото проанализировано"

    monkeypatch.setattr(media_chat_service, "recall", fake_recall)
    monkeypatch.setattr(media_chat_service, "remember", fake_remember)
    monkeypatch.setattr(media_chat_service, "generate_media_reply", vision)

    prompt = "Сравни эту фотографию с прошлой чёрной курткой"
    result = await media_chat_service.reply(Db(), 7, prompt, "image/jpeg", b"image")

    assert result.reply == "Фото проанализировано"
    assert recalled == [prompt]
    assert remembered == [(7, prompt, "user_message")]
