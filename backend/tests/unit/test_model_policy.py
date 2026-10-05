import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_generation_configuration_is_luna_only(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "gpt-6-luna")
    monkeypatch.setenv("GENERATION_PROVIDER", "openai")
    settings = Settings(_env_file=None)
    assert settings.openai_model == "gpt-6-luna"
    with pytest.raises(ValidationError):
        settings.openai_model = "another-model"


@pytest.mark.parametrize("field,value", [
    ("OPENAI_MODEL", "another-model"),
    ("GENERATION_PROVIDER", "ollama"),
])
def test_other_generation_models_and_providers_are_rejected(monkeypatch, field, value):
    monkeypatch.setenv("OPENAI_MODEL", "gpt-6-luna")
    monkeypatch.setenv("GENERATION_PROVIDER", "openai")
    monkeypatch.setenv(field, value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
