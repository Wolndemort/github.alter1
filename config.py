from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Setting(BaseSettings):
    BOT_TOKEN: SecretStr
    GEMINI_API_KEY: SecretStr
    OPENROUTER_API_KEY: SecretStr | None = None
    # Keep local defaults aligned with the documented .env configuration.
    # Environment variables still take precedence over these values.
    OPENROUTER_MODEL: str = "openai/gpt-5.6-luna"
    # Stronger multimodal fallback for image/video analysis. It is used only
    # when paid fallback is enabled, never for ordinary text chat.
    OPENROUTER_VISION_MODEL: str = "google/gemini-3.7-flash"
    # Override these with an available OpenRouter :free model in .env.
    OPENROUTER_FREE_MODEL: str = "nvidia/nemotron-3-super-120b-a12b:free"
    OPENROUTER_FREE_MODEL_2: str = "openai/gpt-oss-20b:free"
    OPENROUTER_FREE_MODEL_3: str = "google/gemma-4-31b-it:free"
    OPENROUTER_FREE_MODEL_4: str = "inclusionai/ling-3.0-tiny:free"
    OPENROUTER_FREE_MODEL_5: str = "nvidia/nemotron-3-nano-30b-a3b:free"
    OPENROUTER_FREE_VISION_MODEL: str = "google/gemma-4-31b-it:free"
    OPENROUTER_FREE_VISION_MODEL_2: str = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"
    OPENROUTER_REASONING_MODEL: str = "inclusionai/ling-2.6-1t"
    OPENROUTER_FALLBACK_MODEL: str = "inclusionai/ling-2.6-flash"
    OPENROUTER_FALLBACK_MODEL_2: str = "openai/gpt-oss-120b"
    # Safety switch: never spend money unless this is explicitly enabled.
    OPENROUTER_ALLOW_PAID_FALLBACK: bool = True
    OPENROUTER_FREE_MODELS_ENABLED: bool = True
    # Prefer a reliable paid model for latency-sensitive chat; free models
    # remain available as fallback when this switch is enabled.
    OPENROUTER_PAID_FIRST: bool = False
    # OpenRouter can suppress provider reasoning from the public stream.
    OPENROUTER_EXCLUDE_REASONING: bool = True
    OWNER_TELEGRAM_IDS: str = "1271717628"
    OWNER_WEB_USER_IDS: str = ""
    OWNER_EMAILS: str = ""
    SUPPORT_USERNAME: str = "Adam_Omarov"
    SUPPORT_TELEGRAM_ID: int = 1271717628
    TELEGRAM_BOT_USERNAME: str = "alter_ai_bot"
    LEGAL_BASE_URL: str = "https://alterai.ru"
    YUKASSA_SHOP_ID: str | None = None
    YUKASSA_SECRET_KEY: SecretStr | None = None
    YUKASSA_RECEIPT_EMAIL: str | None = None
    YUKASSA_SAVE_PAYMENT_METHOD: bool = False
    SUBSCRIPTION_PRICE_RUB: str = "990.00"
    EGO_PRICE_RUB: str = "2990.00"
    PERSONAL_MONTHLY_CREDITS: int = 1000
    EGO_MONTHLY_CREDITS: int = 3500
    SUBSCRIPTION_DAYS: int = 30
    SUBSCRIPTION_RENEWAL_CHECK_SECONDS: int = 3600
    YOUTUBE_API_KEY: SecretStr | None = None
    TAVILY_API_KEY: SecretStr | None = None
    FIRECRAWL_API_KEY: SecretStr | None = None
    GOOGLE_CSE_API_KEY: SecretStr | None = None
    GOOGLE_CSE_ID: str | None = None
    SERPER_API_KEY: SecretStr | None = None
    YANDEX_SEARCH_API_KEY: SecretStr | None = None
    YANDEX_SEARCH_FOLDER_ID: str | None = "b1g884grnt4jatd7bbeo"
    YANDEX_MAPS_GEOCODER_API_KEY: SecretStr | None = None
    YANDEX_MAPS_ORG_API_KEY: SecretStr | None = None
    YANDEX_MAPS_ROUTE_API_KEY: SecretStr | None = None
    YANDEX_MAPS_DISTANCE_MATRIX_API_KEY: SecretStr | None = None
    TWOGIS_API_KEY: SecretStr | None = None
    SEARCH_PROVIDER_TIMEOUT_SECONDS: int = 8
    SEARCH_FAST_RETURN_SECONDS: int = 4
    SEARCH_MIN_RESULTS_BEFORE_FAST_RETURN: int = 3
    SEARCH_PROVIDER_FAILURE_THRESHOLD: int = 3
    SEARCH_PROVIDER_COOLDOWN_SECONDS: int = 60
    # Number of Firecrawl results returned per search, not a monthly quota.
    FIRECRAWL_SEARCH_LIMIT: int = 10
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: SecretStr | None = None
    GOOGLE_REDIRECT_URI: str = "https://api.alterai.ru/api/v1/calendar/oauth/callback"
    TRANSCRIPTION_MODEL: str = "openai/whisper-1"
    TTS_MODEL: str = "openai/gpt-audio-mini"
    TTS_VOICE: str = "alloy"
    TTS_MAX_CHARS: int = 1200
    TTS_MAX_TOKENS: int = 1024
    TTS_AUTO_MAX_CHARS: int = 480
    ELEVENLABS_API_KEY: SecretStr | None = None
    ELEVENLABS_VOICE_ID: str | None = None
    ELEVENLABS_MODEL: str = "eleven_multilingual_v2"
    ELEVENLABS_FAST_MODEL: str = "eleven_flash_v2_5"
    ELEVENLABS_FAST_TIMEOUT_SECONDS: int = 8
    ELEVENLABS_ENABLED: bool = False
    VOICE_REPLY_DEFAULT: bool = True

    # Production must provide DATABASE_URL through .env/docker-compose.
    DATABASE_URL: str = "postgresql+asyncpg://postgres@localhost:5432/alter_project_db"
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CACHE_TTL: int = 3600
    SESSION_TIMEOUT: int = 1800
    # Required for the independent app API. Keep it separate from BOT_TOKEN.
    APP_AUTH_SECRET: SecretStr | None = None
    APP_EMAIL_MODE: str = "console"
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: SecretStr | None = None
    SMTP_FROM_EMAIL: str | None = None
    SMTP_USE_TLS: bool = True

    DAILY_REQUEST_LIMIT: int = 100
    TRIAL_DAYS: int = 3
    TRIAL_CREDITS: int = 40
    MONTHLY_CREDITS: int = 1000
    YOUTUBE_SEARCH_CREDITS: int = 1
    YOUTUBE_AUDIO_CREDITS: int = 10
    SPAM_REQUEST_LIMIT: int = 5
    SPAM_WINDOW_SECONDS: int = 60
    HTTP_RATE_LIMIT: int = 120
    HTTP_RATE_WINDOW_SECONDS: int = 60
    MAX_OUTPUT_TOKENS: int = 600
    LONG_REPLY_MAX_OUTPUT_TOKENS: int = 1200
    # Luna is the paid primary model. Keep enough room for a complete answer
    # so a normal long reply is not mistaken for a provider failure.
    LUNA_MAX_OUTPUT_TOKENS: int = 4096
    MAX_MEMORY_OUTPUT_TOKENS: int = 250
    # Vision replies are conversational answers, not one-line captions. Keep
    # enough room for a conclusion, evidence from the image and a useful next
    # step while still bounding provider cost.
    MAX_MEDIA_OUTPUT_TOKENS: int = 700
    MEDIA_MAX_BYTES: int = 20 * 1024 * 1024
    MEDIA_GENERATION_CREDITS: int = 40
    FAL_TEXT_IMAGE_CREDITS: int = 100
    FAL_TEXT_VIDEO_CREDITS: int = 250
    # Optional OpenAI-compatible media generation provider. The existing
    # OpenRouter chat key is intentionally not reused for binary generation.
    MEDIA_GENERATION_API_URL: str | None = None
    MEDIA_GENERATION_API_KEY: SecretStr | None = None
    MEDIA_PROVIDER: str = "openai_compatible"
    FAL_BASE_URL: str = "https://fal.run"
    FAL_IMAGE_MODEL: str | None = None
    FAL_VIDEO_MODEL: str | None = None
    FAL_TEXT_IMAGE_MODEL: str = "fal-ai/flux-pro/v1.1-ultra"
    FAL_TEXT_VIDEO_MODEL: str = "fal-ai/kling-video/v2.1/master/text-to-video"
    MEDIA_IMAGE_MODEL: str | None = None
    MEDIA_VIDEO_API_URL: str | None = None
    MEDIA_VIDEO_MODEL: str | None = None
    MEDIA_GENERATION_TIMEOUT_SECONDS: int = 180
    MEDIA_GENERATION_RETRY_ATTEMPTS: int = 2
    MEDIA_MAX_OUTPUT_BYTES: int = 50 * 1024 * 1024
    MEDIA_VIDEO_MAX_OUTPUT_BYTES: int = 100 * 1024 * 1024
    # Telegram Bot API rejects oversized uploads; keep a margin below its limit.
    TELEGRAM_MAX_MEDIA_BYTES: int = 49 * 1024 * 1024
    MEDIA_JOB_TTL_SECONDS: int = 86400
    # Keep free-model failures bounded during testing. A long sequential
    # fallback chain otherwise looks like the bot stopped responding.
    AI_TIMEOUT_SECONDS: int = 15
    AI_STREAM_MODEL_TIMEOUT_SECONDS: int = 10
    AI_STREAM_MAX_MODELS: int = 2
    # Temporarily move models that return transient provider errors to the end
    # of the fallback route instead of retrying them on every new message.
    AI_MODEL_COOLDOWN_SECONDS: int = 60
    AI_DEEP_REVIEW_ENABLED: bool = False
    AI_DEEP_REVIEW_MAX_TOKENS: int = 900
    TOOL_MAX_ROUNDS: int = 2
    AI_TOOL_TIMEOUT_SECONDS: int = 12
    AI_MAX_PROMPT_CHARS: int = 8000
    PAYMENT_WEBHOOK_HOST: str = "0.0.0.0"
    PAYMENT_WEBHOOK_PORT: int = 8080
    PAYMENT_WEBHOOK_PATH: str = "/webhooks/yookassa"
    MEMORY_RECALL_LIMIT: int = 3
    MEMORY_RECALL_MAX_DISTANCE: float = 0.35
    MEMORY_AUTO_RECALL_MIN_CHARS: int = 8
    MEMORY_PROMPT_MAX_CHARS: int = 4500
    MEMORY_SUMMARY_MAX_CHARS: int = 7000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


config = Setting()
