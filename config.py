from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr


class Setting(BaseSettings):
    BOT_TOKEN: SecretStr

    GEMINI_API_KEY: SecretStr

    DATABASE_URL: str = "postgresql+asyncpg://postgres:lordwolndemort0195@alter_db_container:5432/alter_project_db"

    SESSION_TIMEOUT: int = 1800

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


config = Setting()
