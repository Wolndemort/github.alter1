"""Canonical public capability catalog; descriptions must match implemented routes."""
from __future__ import annotations

CAPABILITY_CATALOG = {
    "conversation": ["text_chat", "streaming", "memory", "new_sessions", "feedback"],
    "agent": ["durable_task_graph", "dependencies", "deadlines", "priorities", "replan", "tool_execution", "external_action_gate"],
    "web": ["source_attributed_search", "Yandex_search", "Tavily", "Firecrawl", "YouTube_search", "weather"],
    "maps": ["device_location_with_consent", "Yandex_geocode", "organization_search", "route", "distance_matrix"],
    "documents": ["PDF_read", "DOCX_read", "TXT_MD_CSV_JSON_read", "OCR", "document_profile", "document_agent", "document_edit_export", "version_compare"],
    "vision": ["image_analysis", "OCR", "structured_visual_audit", "object_geometry", "chart_data", "confidence_gate", "image_editing"],
    "video": ["frame_sampling", "audio_extraction", "transcription", "timestamped_events", "video_generation", "image_to_video"],
    "audio": ["speech_to_text", "text_to_speech", "voice_change", "audio_isolation", "sound_effects", "audio_mix", "YouTube_audio"],
    "productivity": ["reminders", "push_notifications", "checkins", "Google_Calendar", "location_context"],
    "operations": ["fallback_models", "quality_gate", "latency_metrics", "owner_diagnostics", "quotas", "backup_scripts", "production_smoke"],
}


def capability_catalog_text() -> str:
    return "\n".join(f"{category}: {', '.join(items)}" for category, items in CAPABILITY_CATALOG.items())
