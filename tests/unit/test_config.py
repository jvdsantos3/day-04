"""Unit tests for application settings (T2)."""

import pytest

from financial_assistant.config import Settings, get_settings

pytestmark = pytest.mark.unit

ENV_VARS = [
    "DATABASE_URL",
    "CHROMA_PATH",
    "JWT_SECRET",
    "JWT_EXPIRE_MINUTES",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "HF_HOME",
]


@pytest.fixture(autouse=True)
def _clear_settings_env(monkeypatch):
    """Isolate each test from the ambient environment and the settings cache."""
    for var in ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_defaults_applied_when_env_absent():
    settings = Settings(_env_file=None)

    assert settings.database_url == "sqlite:///./data/finance.db"
    assert settings.chroma_path == "./data/chroma"
    assert settings.jwt_secret == "change-me-in-production"
    assert settings.jwt_expire_minutes == 1440
    assert settings.deepseek_api_key == ""
    assert settings.deepseek_base_url == "https://api.deepseek.com"
    assert settings.hf_home is None


def test_loads_all_values_from_env_vars(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/other.db")
    monkeypatch.setenv("CHROMA_PATH", "/var/chroma")
    monkeypatch.setenv("JWT_SECRET", "super-secret")
    monkeypatch.setenv("JWT_EXPIRE_MINUTES", "30")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-123")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://proxy.example.com/v1")
    monkeypatch.setenv("HF_HOME", "/models/hf")

    settings = Settings(_env_file=None)

    assert settings.database_url == "sqlite:///./data/other.db"
    assert settings.chroma_path == "/var/chroma"
    assert settings.jwt_secret == "super-secret"
    assert settings.jwt_expire_minutes == 30
    assert settings.deepseek_api_key == "sk-deepseek-123"
    assert settings.deepseek_base_url == "https://proxy.example.com/v1"
    assert settings.hf_home == "/models/hf"


def test_jwt_expire_minutes_coerced_to_int(monkeypatch):
    monkeypatch.setenv("JWT_EXPIRE_MINUTES", "90")

    settings = Settings(_env_file=None)

    assert settings.jwt_expire_minutes == 90
    assert isinstance(settings.jwt_expire_minutes, int)


def test_get_settings_returns_cached_singleton():
    first = get_settings()
    second = get_settings()

    assert first is second


def test_get_settings_reads_environment(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "from-env")
    get_settings.cache_clear()

    assert get_settings().jwt_secret == "from-env"
