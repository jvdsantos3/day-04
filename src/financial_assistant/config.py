"""Application settings loaded from environment variables / .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the financial assistant.

    Values are read from environment variables (case-insensitive) with a
    fallback to a local ``.env`` file. Environment variables take precedence.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Structured persistence (SQLite = source of truth)
    database_url: str = "sqlite:///./data/finance.db"

    # Vector persistence (ChromaDB semantic index)
    chroma_path: str = "./data/chroma"

    # Auth — JWT session cookie (HS256)
    jwt_secret: str = "change-me-in-production"
    jwt_expire_minutes: int = 1440

    # LLM — DeepSeek via OpenAI-compatible API
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"

    # HuggingFace cache dir for the local embedding model (optional)
    hf_home: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Return the singleton :class:`Settings` instance."""
    return Settings()
