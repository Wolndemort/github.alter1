"""Media chat use case shared by the mobile HTTP adapter."""
from __future__ import annotations

import base64
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import config
from data.models import Session, User
from services.chat_service import _append, validate_message
from utils.media import video_audio, video_duration, video_preview
from services.media_quality import video_context
from utils.media_logic import generate_media_reply, extract_visual_context
from utils.voice import transcribe_voice
from utils.generation_intent import generation_kind
from services.media_generation import generate_image, generate_video
from utils.vector_memory import recall, remember
from services.elevenlabs_media import ElevenLabsError, design_voice, speech_to_speech
from services.voice_commands import is_voice_change_request, is_voice_generation_request, requested_voice_id, voice_description
from utils.feedback_memory import feedback_context
from utils.quality import sanitize_public_reply
from utils.intent import should_recall_context
from utils.multimodal_context import attachment_context_message
from services.artifact_store import latest_artifact, save_artifact
from utils.document_commands import is_document_save_request
import re


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
    artifact_id: str | None = None


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
    ).order_by(Session.started_at.desc()).limit(1))
    session = result.scalar_one_or_none()
    if session is None:
        session = Session(user_id=user_id, raw_messages=[])
        db.add(session)
        await db.flush()
    return session


def _record_attachment_context(session: Session, *, kind: str, filename: str, media_type: str,
                               operation: str, transcript: str = "", observation: str = "",
                               profile: dict | None = None, artifact_filename: str = "",
                               artifact_media_type: str = "", artifact_id: str = "") -> None:
    _append(session, "assistant", attachment_context_message(
        kind=kind, filename=filename, media_type=media_type, operation=operation,
        transcript=transcript, observation=observation, profile=profile,
        artifact_filename=artifact_filename, artifact_media_type=artifact_media_type,
        artifact_id=artifact_id,
    ))


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
        if is_voice_change_request(prompt):
            voice_id = requested_voice_id(prompt, (user.tech_stack or {}).get("generated_voice_id"), config.ELEVENLABS_VOICE_ID)
            if not voice_id:
                raise ValueError("Сначала создай голос или укажи voice_id.")
            try:
                transformed = await speech_to_speech(data, voice_id, filename)
            except ElevenLabsError as exc:
                raise ValueError(str(exc)) from exc
            _append(session, "user", prompt)
            _append(session, "assistant", "Изменил голос записи.")
            artifact_id = await save_artifact(user_id, transformed, "alter-voice.mp3", "audio/mpeg", kind=kind, operation="voice_change")
            _record_attachment_context(session, kind=kind, filename=filename, media_type=content_type,
                                       operation="voice_change", artifact_filename="alter-voice.mp3",
                                       artifact_media_type="audio/mpeg", artifact_id=artifact_id)
            await db.commit()
            return MediaChatResult(reply="Изменил голос записи.", session_id=session.id, audio=transformed, audio_filename="alter-voice.mp3", artifact_id=artifact_id)
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
            artifact_id = await save_artifact(user_id, audio, "alter-audio.mp3", "audio/mpeg", kind=kind, operation="audio_action")
            _append(session, "user", prompt)
            _append(session, "assistant", answer)
            _record_attachment_context(session, kind=kind, filename=filename, media_type=content_type,
                                       operation="audio_action", transcript=transcript or prompt,
                                       artifact_filename="alter-audio.mp3", artifact_media_type="audio/mpeg", artifact_id=artifact_id)
            await remember(db, user_id, prompt, source="user_message")
            await db.commit()
            return MediaChatResult(reply=answer, session_id=session.id, transcript=transcript, audio=audio, audio_filename="alter-audio.mp3", artifact_id=artifact_id)
        if transcript is None:
            transcript = await transcribe_voice(data)
        if not transcript:
            raise ValueError("voice message could not be transcribed")
        prompt = transcript
        if is_document_save_request(prompt):
            artifact = await latest_artifact(user_id, kind="document")
            artifact_data = b""
            if artifact:
                try:
                    artifact_data = base64.b64decode(artifact.get("data_base64", ""), validate=True)
                except (ValueError, TypeError):
                    artifact_data = b""
            if artifact_data:
                reply = "Файл подготовлен. Его можно скачать из чата."
                _append(session, "user", prompt)
                _append(session, "assistant", reply)
                await db.commit()
                return MediaChatResult(reply=reply, session_id=session.id, transcript=transcript, media_data=artifact_data, media_filename=artifact.get("filename"), media_type=artifact.get("media_type"), artifact_id=artifact.get("id"))
            return MediaChatResult(reply="У меня нет подготовленного файла для сохранения. Сначала прикрепи документ и выбери «Изменить и сохранить».", session_id=session.id, transcript=transcript)
        if is_voice_generation_request(prompt):
            description = voice_description(prompt)
            if not description:
                raise ValueError("voice description required")
            try:
                generated = await design_voice(description)
            except ElevenLabsError as exc:
                raise ValueError(str(exc)) from exc
            voice_id = str(generated.get("voice_id") or generated.get("id") or "").strip()
            if voice_id:
                settings = dict(user.tech_stack or {})
                settings["generated_voice_id"] = voice_id
                user.tech_stack = settings
            previews = generated.get("previews") if isinstance(generated, dict) else None
            preview = next((item for item in previews if isinstance(item, dict)), None) if isinstance(previews, list) else None
            encoded = preview.get("audio_base_64") or preview.get("audio_base64") if preview else None
            reply = "Голос создан в ALTER. Вот его пробное звучание." if voice_id else "Голос сгенерирован. Вот пробное звучание."
            preview_data = base64.b64decode(encoded) if encoded else b""
            artifact_id = await save_artifact(user_id, preview_data, "alter-voice-preview.mp3", "audio/mpeg", kind=kind, operation="voice_generation") if preview_data else ""
            _append(session, "user", prompt)
            _append(session, "assistant", reply)
            _record_attachment_context(session, kind=kind, filename=filename, media_type=content_type,
                                       operation="voice_generation", transcript=transcript,
                                       artifact_filename="alter-voice-preview.mp3", artifact_media_type="audio/mpeg", artifact_id=artifact_id)
            await db.commit()
            return MediaChatResult(reply=reply, session_id=session.id, transcript=transcript, audio=preview_data or None, audio_filename="alter-voice-preview.mp3", artifact_id=artifact_id or None)
        if generation_kind(prompt) == "image":
            artifact = await generate_image(prompt)
            artifact_id = await save_artifact(user_id, artifact.data, artifact.filename, artifact.media_type, kind="image", operation="image_generation")
            _append(session, "user", prompt)
            _append(session, "assistant", "Создал изображение.")
            _record_attachment_context(session, kind=kind, filename=filename, media_type=content_type,
                                       operation="image_generation", transcript=transcript,
                                       artifact_filename=artifact.filename, artifact_media_type=artifact.media_type, artifact_id=artifact_id)
            await remember(db, user_id, prompt, source="user_message")
            await db.commit()
            return MediaChatResult(
                reply="Создал изображение.", session_id=session.id, transcript=transcript,
                media_data=artifact.data, media_filename=artifact.filename, media_type=artifact.media_type, artifact_id=artifact_id,
            )
        if generation_kind(prompt) == "video":
            artifact = await generate_video(prompt)
            artifact_id = await save_artifact(user_id, artifact.data, artifact.filename, artifact.media_type, kind="video", operation="video_generation")
            _append(session, "user", prompt)
            _append(session, "assistant", "Создал видео.")
            _record_attachment_context(session, kind=kind, filename=filename, media_type=content_type,
                                       operation="video_generation", transcript=transcript,
                                       artifact_filename=artifact.filename, artifact_media_type=artifact.media_type, artifact_id=artifact_id)
            await remember(db, user_id, prompt, source="user_message")
            await db.commit()
            return MediaChatResult(
                reply="Создал видео.", session_id=session.id, transcript=transcript,
                media_data=artifact.data, media_filename=artifact.filename, media_type=artifact.media_type, artifact_id=artifact_id,
            )
        from services.chat_service import ChatService
        _record_attachment_context(session, kind=kind, filename=filename, media_type=content_type,
                                   operation="transcription", transcript=transcript)
        result = await ChatService().reply(db, user_id, prompt)
        return MediaChatResult(reply=result.reply, session_id=result.session_id, transcript=transcript)
    # Image edit/animation requests must use the source image.  Otherwise the
    # mobile multipart route falls through to vision chat and only describes it.
    if kind == "image" and prompt.strip():
        value = prompt.casefold().replace("ё", "е")
        animate = bool(re.search(r"(?:ожив|анимац|движени|сделай\s+видео|сделай\s+ролик|преврати\s+в\s+видео)", value))
        edit = bool(re.search(r"(?:измени|изменить|поменяй|поменять|замени|убери|добавь|сделай|улучш|перерис|обработай|edit|change|remove|add)", value))
        if animate or edit:
            artifact = await (generate_video(prompt, (content_type or "image/jpeg", data)) if animate else generate_image(prompt, (content_type or "image/jpeg", data)))
            operation = "image_animation" if animate else "image_edit"
            reply_text = "Оживил изображение." if animate else "Изменил изображение по твоему описанию."
            artifact_id = await save_artifact(user_id, artifact.data, artifact.filename, artifact.media_type, kind="video" if animate else "image", operation=operation)
            _append(session, "user", prompt)
            _append(session, "assistant", reply_text)
            _record_attachment_context(session, kind=kind, filename=filename, media_type=content_type,
                                       operation=operation, artifact_filename=artifact.filename,
                                       artifact_media_type=artifact.media_type, artifact_id=artifact_id)
            await remember(db, user_id, prompt, source="user_message")
            await db.commit()
            return MediaChatResult(reply=reply_text, session_id=session.id, media_data=artifact.data,
                                   media_filename=artifact.filename, media_type=artifact.media_type, artifact_id=artifact_id)
    transcript = None
    analysis_prompt = prompt
    media = [("image/jpeg" if kind == "image" else "video/mp4", data)]
    if kind == "video":
        media = await video_preview(data)
        if not media:
            raise ValueError("video could not be processed")
        audio = await video_audio(data)
        quality = video_context(duration_seconds=await video_duration(data), frame_count=len(media), transcript="")
        analysis_prompt += f"\n\nTechnical video quality context: {quality}"
        if audio:
            transcript = await transcribe_voice(audio)
            if transcript:
                analysis_prompt = (
                    f"{prompt}\n\nТранскрипт аудиодорожки видео (используй только как дополнительный контекст):\n{transcript[:12000]}"
                )
    _append(session, "user", prompt)
    memory = dict(user.memory or {})
    feedback = feedback_context(user.tech_stack)
    if feedback:
        memory["response_feedback"] = feedback
    if should_recall_context(prompt):
        recalled = await recall(db, user_id, prompt)
        if recalled:
            memory["related_previous_context"] = recalled
    answer = sanitize_public_reply(await generate_media_reply(analysis_prompt, media, memory=memory, conversation_context=session.raw_messages[:-1]))
    try:
        visual = await extract_visual_context(prompt, media)
        if visual:
            _record_attachment_context(
                session, kind=kind, filename=filename, media_type=content_type,
                operation="analysis", transcript=transcript or "", observation=str(visual),
                profile={"video": quality} if kind == "video" else {},
            )
    except Exception:
        pass
    _append(session, "assistant", answer)
    await remember(db, user_id, prompt, source="user_message")
    await db.commit()
    return MediaChatResult(reply=answer, session_id=session.id, transcript=transcript)
