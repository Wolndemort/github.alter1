from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Setting(BaseSettings):
    BOT_TOKEN: SecretStr
    GEMINI_API_KEY: SecretStr
    OPENROUTER_API_KEY: SecretStr | None = None
    # Keep local defaults aligned with the documented .env configuration.
    # Environment variables still take precedence over these values.
    OPENROUTER_MODEL: str = "google/gemini-2.5-flash"
    OPENROUTER_REASONING_MODEL: str = "google/gemini-2.5-pro"
    OPENROUTER_FALLBACK_MODEL: str = "openai/gpt-4o-mini"
    OPENROUTER_FALLBACK_MODEL_2: str = "anthropic/claude-3.5-haiku"
    YOUTUBE_API_KEY: SecretStr | None = None
    TAVILY_API_KEY: SecretStr | None = None
    TRANSCRIPTION_MODEL: str = "openai/whisper-1"
    TTS_MODEL: str = "openai/gpt-audio-mini"
    TTS_VOICE: str = "alloy"
    TTS_MAX_CHARS: int = 1200
    TTS_MAX_TOKENS: int = 1024
    VOICE_REPLY_DEFAULT: bool = True

    DATABASE_URL: str = "postgresql+asyncpg://postgres:lordwolndemort0195@alter_db_container:5432/alter_project_db"
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CACHE_TTL: int = 3600
    SESSION_TIMEOUT: int = 1800

    DAILY_REQUEST_LIMIT: int = 100
    SPAM_REQUEST_LIMIT: int = 5
    SPAM_WINDOW_SECONDS: int = 60
    MAX_OUTPUT_TOKENS: int = 350
    MAX_MEMORY_OUTPUT_TOKENS: int = 250
    MAX_MEDIA_OUTPUT_TOKENS: int = 300
    AI_TIMEOUT_SECONDS: int = 45

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


config = Setting()
