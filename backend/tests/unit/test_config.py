import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


@pytest.fixture(autouse=True)
def isolate_environment(monkeypatch):
    for name in ("APP_NAME", "APP_ENV", "CORS_ORIGINS"):
        monkeypatch.delenv(name, raising=False)


def test_defaults_without_env_file():
    settings = Settings(_env_file=None)
    assert settings.app_name == "Lenny Growth Assistant API"
    assert settings.app_env == "development"
    assert settings.cors_origins == [
        "http://localhost:5173", "http://127.0.0.1:5173"
    ]


@pytest.mark.parametrize(
    "values,field",
    [({"app_env": "staging"}, "app_env"),
     ({"cors_origins": [123]}, "cors_origins")],
)
def test_invalid_values_are_rejected(values, field):
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, **values)
    assert error.value.errors()[0]["loc"][0] == field


def test_cache_reuses_settings_until_cleared(monkeypatch):
    monkeypatch.setenv("APP_NAME", "Before change")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("CORS_ORIGINS", "[]")
    get_settings.cache_clear()
    try:
        original = get_settings()
        monkeypatch.setenv("APP_NAME", "After change")
        assert get_settings() is original
        assert get_settings().app_name == "Before change"
        get_settings.cache_clear()
        refreshed = get_settings()
        assert refreshed is not original
        assert refreshed.app_name == "After change"
    finally:
        get_settings.cache_clear()


def test_environment_overrides_dotenv(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        'APP_NAME="File name"\nCORS_ORIGINS=["https://frontend.example"]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("APP_NAME", "Environment name")
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    settings = Settings(_env_file=env_file)
    assert settings.app_name == "Environment name"
    assert settings.cors_origins == ["https://frontend.example"]
