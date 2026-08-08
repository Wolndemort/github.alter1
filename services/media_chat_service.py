"""Media chat use case shared by the mobile HTTP adapter."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import config
from data.models import Session, User
from services.chat_service import _append, validate_message
from utils.media import video_preview
from utils.media_logic import generate_media_reply
from utils.voice import transcribe_voice


@dataclass(frozen=True)
class MediaChatResult:
    reply: str
    session_id: int
    transcript: str | None = None
    audio: bytes | None = None
    audio_filename: str | None = None


def validate_media(content_type: str, data: bytes) -> str:
    if len(data) > config.MEDIA_MAX_BYTES:
        raise ValueError("media file is too large")
    if content_type.startswith("image/"):
        return "image"
    if content_type.startswith("video/"):
        return "video"
    if content_type.startswith("audio/"):
        return "audio"
    raise ValueError("unsupported media type")


async def _active_session(db: AsyncSession, user_id: int) -> Session:
    result = await db.execute(select(Session).where(
        Session.user_id == user_id, Session.is_processed.is_(False)
    ).order_by(Session.started_at.desc()))
    session = result.scalar_one_or_none()
    if session is None:
        session = Session(user_id=user_id, raw_messages=[])
        db.add(session)
        await db.flush()
    return session


async def reply(db: AsyncSession, user_id: int, prompt: str, content_type: str, data: bytes, filename: str = "audio.m4a") -> MediaChatResult:
    kind = validate_media(content_type, data)
    user = await db.get(User, user_id)
    if user is None:
        raise ValueError("user not found")
    session = await _active_session(db, user_id)
    prompt = validate_message(prompt or "Проанализируй это вложение")
    if kind == "audio":
        from utils.audio_actions import process_audio_action
        action_result = await process_audio_action(prompt, data, filename)
        if action_result:
            answer, audio = action_result
            _append(session, "user", prompt)
            _append(session, "assistant", answer)
            await db.commit()
            return MediaChatResult(reply=answer, session_id=session.id, audio=audio, audio_filename="alter-audio.mp3")
        transcript = await transcribe_voice(data)
        if not transcript:
            raise ValueError("voice message could not be transcribed")
        prompt = transcript
        from services.chat_service import ChatService
        result = await ChatService().reply(db, user_id, prompt)
        return MediaChatResult(reply=result.reply, session_id=result.session_id, transcript=transcript)
    media = [("image/jpeg" if kind == "image" else "video/mp4", data)]
    if kind == "video":
        media = await video_preview(data)
        if not media:
            raise ValueError("video could not be processed")
    _append(session, "user", prompt)
    answer = await generate_media_reply(prompt, media, memory=dict(user.memory or {}), conversation_context=session.raw_messages[:-1])
    _append(session, "assistant", answer)
    await db.commit()
    return MediaChatResult(reply=answer, session_id=session.id)
