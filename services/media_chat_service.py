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
from utils.generation_intent import generation_kind
from services.media_generation import generate_image, generate_video
from utils.vector_memory import recall, remember


@dataclass(frozen=True)
class MediaChatResult:
    reply: str
    session_id: int
    transcript: str | None = None
    audio: bytes | None = None
    audio_filename: str | None = None
    media_data: bytes | None = None
    media_filename: str | None = None
    media_type: str | None = None


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
    default_prompt = "Проанализируй это вложение"
    prompt = validate_message(prompt or default_prompt)
    if kind == "audio":
        from utils.audio_actions import process_audio_action
        # A mobile voice command is inside the uploaded audio, not in the
        # multipart text field. Transcribe it before routing audio actions;
        # otherwise ALTER treats "наложи дождь..." as ordinary chat and only
        # returns a transcript.
        transcript = None
        if prompt == default_prompt:
            transcript = await transcribe_voice(data)
            if not transcript:
                raise ValueError("voice message could not be transcribed")
            prompt = transcript
        action_result = await process_audio_action(prompt, data, filename)
        if action_result:
            answer, audio = action_result
            _append(session, "user", prompt)
            _append(session, "assistant", answer)
            await remember(db, user_id, prompt, source="user_message")
            await db.commit()
            return MediaChatResult(reply=answer, session_id=session.id, transcript=transcript, audio=audio, audio_filename="alter-audio.mp3")
        if transcript is None:
            transcript = await transcribe_voice(data)
        if not transcript:
            raise ValueError("voice message could not be transcribed")
        prompt = transcript
        if generation_kind(prompt) == "image":
            artifact = await generate_image(prompt)
            _append(session, "user", prompt)
            _append(session, "assistant", "Создал изображение.")
            await remember(db, user_id, prompt, source="user_message")
            await db.commit()
            return MediaChatResult(
                reply="Создал изображение.", session_id=session.id, transcript=transcript,
                media_data=artifact.data, media_filename=artifact.filename, media_type=artifact.media_type,
            )
        if generation_kind(prompt) == "video":
            artifact = await generate_video(prompt)
            _append(session, "user", prompt)
            _append(session, "assistant", "Создал видео.")
            await remember(db, user_id, prompt, source="user_message")
            await db.commit()
            return MediaChatResult(
                reply="Создал видео.", session_id=session.id, transcript=transcript,
                media_data=artifact.data, media_filename=artifact.filename, media_type=artifact.media_type,
            )
        from services.chat_service import ChatService
        result = await ChatService().reply(db, user_id, prompt)
        return MediaChatResult(reply=result.reply, session_id=result.session_id, transcript=transcript)
    media = [("image/jpeg" if kind == "image" else "video/mp4", data)]
    if kind == "video":
        media = await video_preview(data)
        if not media:
            raise ValueError("video could not be processed")
    _append(session, "user", prompt)
    memory = dict(user.memory or {})
    if len(prompt) >= config.MEMORY_AUTO_RECALL_MIN_CHARS:
        recalled = await recall(db, user_id, prompt)
        if recalled:
            memory["related_previous_context"] = recalled
    answer = await generate_media_reply(prompt, media, memory=memory, conversation_context=session.raw_messages[:-1])
    _append(session, "assistant", answer)
    await remember(db, user_id, prompt, source="user_message")
    await db.commit()
    return MediaChatResult(reply=answer, session_id=session.id)
