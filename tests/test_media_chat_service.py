from types import SimpleNamespace

import pytest

from data.models import Session, User
from services import media_chat_service


class Result:
    def scalar_one_or_none(self): return None


class Db:
    def __init__(self): self.user = User(id=7, first_name="Test", memory={"goals": ["ship"]}, tech_stack={}); self.added = []; self.committed = False
    async def get(self, model, user_id): return self.user if user_id == 7 else None
    async def execute(self, statement): return Result()
    def add(self, value):
        if isinstance(value, Session): value.id = 11
        self.added.append(value)
    async def flush(self): pass
    async def commit(self): self.committed = True


def test_validate_media_rejects_unknown_and_oversized(monkeypatch):
    assert media_chat_service.validate_media("image/jpeg", b"x") == "image"
    assert media_chat_service.validate_media("video/mp4", b"x") == "video"
    assert media_chat_service.validate_media("audio/m4a", b"x") == "audio"
    with pytest.raises(ValueError, match="unsupported"):
        media_chat_service.validate_media("text/plain", b"x")
    monkeypatch.setattr(media_chat_service.config, "MEDIA_MAX_BYTES", 1)
    with pytest.raises(ValueError, match="too large"):
        media_chat_service.validate_media("image/jpeg", b"xx")


@pytest.mark.asyncio
async def test_image_reply_uses_vision_and_shared_session(monkeypatch):
    async def vision(prompt, media, **kwargs):
        assert media[0][0] == "image/jpeg" and media[0][1] == b"image"
        return "vision reply"
    monkeypatch.setattr(media_chat_service, "generate_media_reply", vision)
    result = await media_chat_service.reply(Db(), 7, "what is this", "image/jpeg", b"image")
    assert result.reply == "vision reply" and result.session_id == 11


@pytest.mark.asyncio
async def test_video_requires_extractable_preview(monkeypatch):
    async def no_preview(data): return []
    monkeypatch.setattr(media_chat_service, "video_preview", no_preview)
    with pytest.raises(ValueError, match="could not be processed"):
        await media_chat_service.reply(Db(), 7, "", "video/mp4", b"video")


@pytest.mark.asyncio
async def test_video_reply_combines_frames_with_audio_transcript(monkeypatch):
    captured = {}

    async def preview(data): return [("image/jpeg", b"frame")]
    async def audio(data): return b"audio"
    async def transcribe(data): return "Человек говорит о сроках проекта"
    async def vision(prompt, media, **kwargs):
        captured["prompt"] = prompt
        assert media == [("image/jpeg", b"frame")]
        return "Понял видео"

    monkeypatch.setattr(media_chat_service, "video_preview", preview)
    monkeypatch.setattr(media_chat_service, "video_audio", audio)
    monkeypatch.setattr(media_chat_service, "transcribe_voice", transcribe)
    monkeypatch.setattr(media_chat_service, "generate_media_reply", vision)
    result = await media_chat_service.reply(Db(), 7, "Разбери видео", "video/mp4", b"video")
    assert result.reply == "Понял видео"
    assert result.transcript == "Человек говорит о сроках проекта"
    assert "Транскрипт аудиодорожки видео" in captured["prompt"]


@pytest.mark.asyncio
async def test_audio_is_transcribed_and_delegated_to_text_chat(monkeypatch):
    async def transcribe(data): return "transcribed message"
    monkeypatch.setattr(media_chat_service, "transcribe_voice", transcribe)
    class Result:
        reply = "text reply"
        session_id = 12
    async def chat(self, db, user_id, text):
        assert text == "transcribed message"
        return Result()
    monkeypatch.setattr("services.chat_service.ChatService.reply", chat)
    result = await media_chat_service.reply(Db(), 7, "", "audio/m4a", b"audio")
    assert result.reply == "text reply"


@pytest.mark.asyncio
async def test_voice_command_is_processed_as_audio_action_before_chat(monkeypatch):
    async def transcribe(data):
        return "Наложи шум дождя на моё голосовое"

    async def action(prompt, data, filename):
        assert prompt == "Наложи шум дождя на моё голосовое"
        assert data == b"audio"
        return "Наложил дождь", b"mixed-mp3"

    monkeypatch.setattr(media_chat_service, "transcribe_voice", transcribe)
    monkeypatch.setattr("utils.audio_actions.process_audio_action", action)
    result = await media_chat_service.reply(Db(), 7, "", "audio/m4a", b"audio")
    assert result.reply == "Наложил дождь"
    assert result.transcript == "Наложи шум дождя на моё голосовое"
    assert result.audio == b"mixed-mp3"


@pytest.mark.asyncio
async def test_voice_generation_command_returns_real_image_artifact(monkeypatch):
    async def transcribe(data): return "Создай красивое фото девушки"

    async def generate(prompt):
        assert "фото" in prompt
        return SimpleNamespace(data=b"png", filename="alter.png", media_type="image/png")

    monkeypatch.setattr(media_chat_service, "transcribe_voice", transcribe)
    monkeypatch.setattr(media_chat_service, "generate_image", generate)
    result = await media_chat_service.reply(Db(), 7, "", "audio/m4a", b"audio")
    assert result.media_data == b"png"
    assert result.media_filename == "alter.png"
    assert result.media_type == "image/png"
