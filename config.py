from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Setting(BaseSettings):
    BOT_TOKEN: SecretStr
    GEMINI_API_KEY: SecretStr
    OPENROUTER_API_KEY: SecretStr | None = None
    # Keep local defaults aligned with the documented .env configuration.
    # Environment variables still take precedence over these values.
    OPENROUTER_MODEL: str = "openai/gpt-5.6-luna"
    # Override these with an available OpenRouter :free model in .env.
    OPENROUTER_FREE_MODEL: str = "google/gemma-4-31b-it:free"
    OPENROUTER_FREE_MODEL_2: str = "inclusionai/ling-3.0-flash:free"
    OPENROUTER_FREE_MODEL_3: str = "nvidia/nemotron-3-super-120b-a12b:free"
    OPENROUTER_FREE_MODEL_4: str = "google/gemma-4-26b-a4b-it:free"
    OPENROUTER_FREE_MODEL_5: str = "openai/gpt-oss-20b:free"
    OPENROUTER_FREE_VISION_MODEL: str = "google/gemma-4-31b-it:free"
    OPENROUTER_FREE_VISION_MODEL_2: str = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"
    OPENROUTER_REASONING_MODEL: str = "inclusionai/ling-2.6-1t"
    OPENROUTER_FALLBACK_MODEL: str = "inclusionai/ling-2.6-flash"
    OPENROUTER_FALLBACK_MODEL_2: str = "openai/gpt-5.6-terra"
    # Safety switch: never spend money unless this is explicitly enabled.
    OPENROUTER_ALLOW_PAID_FALLBACK: bool = False
    OWNER_TELEGRAM_IDS: str = "1271717628"
    SUPPORT_USERNAME: str = "Adam_Omarov"
    SUPPORT_TELEGRAM_ID: int = 1271717628
    LEGAL_BASE_URL: str = "https://alterai.ru"
    YUKASSA_SHOP_ID: str | None = None
    YUKASSA_SECRET_KEY: SecretStr | None = None
    YUKASSA_RECEIPT_EMAIL: str | None = None
    SUBSCRIPTION_PRICE_RUB: str = "490.00"
    SUBSCRIPTION_DAYS: int = 30
    SUBSCRIPTION_RENEWAL_CHECK_SECONDS: int = 3600
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
    MAX_OUTPUT_TOKENS: int = 600
    MAX_MEMORY_OUTPUT_TOKENS: int = 250
    MAX_MEDIA_OUTPUT_TOKENS: int = 300
    # Keep free-model failures bounded during testing. A long sequential
    # fallback chain otherwise looks like the bot stopped responding.
    AI_TIMEOUT_SECONDS: int = 20
    # Temporarily move models that return transient provider errors to the end
    # of the fallback route instead of retrying them on every new message.
    AI_MODEL_COOLDOWN_SECONDS: int = 60
    AI_DEEP_REVIEW_ENABLED: bool = True
    AI_DEEP_REVIEW_MAX_TOKENS: int = 900
    TOOL_MAX_ROUNDS: int = 2
    AI_MAX_PROMPT_CHARS: int = 12000
    PAYMENT_WEBHOOK_HOST: str = "0.0.0.0"
    PAYMENT_WEBHOOK_PORT: int = 8080
    PAYMENT_WEBHOOK_PATH: str = "/webhooks/yookassa"
    MEMORY_RECALL_LIMIT: int = 3
    MEMORY_RECALL_MAX_DISTANCE: float = 0.35
    MEMORY_AUTO_RECALL_MIN_CHARS: int = 40
    MEMORY_PROMPT_MAX_CHARS: int = 4500
    MEMORY_SUMMARY_MAX_CHARS: int = 7000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


config = Setting()
