"""Tests for Vision provider routing.

The point of these is narrow but important: the demo must never *think* it is
doing real classification while it is actually returning a canned label, and
switching to a real provider must not require a code change.
"""

import pytest
from pydantic import ValidationError

from src.config import get_settings
from src.services.vision import VisionProviderError, get_vision_model


@pytest.fixture
def settings_env(monkeypatch):
    """Set vision env vars and clear the settings cache around the test."""

    def _apply(**values):
        for key, value in values.items():
            monkeypatch.setenv(key, value)
        get_settings.cache_clear()
        return get_settings()

    get_settings.cache_clear()
    yield _apply
    get_settings.cache_clear()


def test_stub_provider_returns_the_canned_label(settings_env):
    settings_env(
        VISION_PROVIDER="stub",
        STUB_VISION_LABEL="metal",
        STUB_VISION_CONFIDENCE="0.77",
    )
    model = get_vision_model()

    assert type(model).__name__ == "_StubVisionModel"


def test_openai_provider_without_a_key_fails_loudly(settings_env):
    """Better a startup error than a demo that silently classifies nothing."""
    settings_env(VISION_PROVIDER="openai", OPENAI_API_KEY="")

    with pytest.raises(VisionProviderError, match="OPENAI_API_KEY"):
        get_vision_model()


def test_openai_provider_defaults_to_openai_itself(settings_env):
    settings_env(
        VISION_PROVIDER="openai",
        OPENAI_API_KEY="sk-test-not-real",
        VISION_MODEL_NAME="gpt-4o-mini",
        VISION_BASE_URL="",
    )
    model = get_vision_model()

    assert model.model_name == "gpt-4o-mini"
    # No base URL configured means the SDK's own default, not an empty string.
    assert model.openai_api_base is None


def test_base_url_routes_to_an_openai_compatible_endpoint(settings_env):
    """A free Gemini or OpenRouter key must work without touching the code."""
    settings_env(
        VISION_PROVIDER="openai",
        OPENAI_API_KEY="sk-test-not-real",
        VISION_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai/",
        VISION_MODEL_NAME="gemini-2.5-flash",
    )
    model = get_vision_model()

    assert model.model_name == "gemini-2.5-flash"
    assert model.openai_api_base == (
        "https://generativelanguage.googleapis.com/v1beta/openai/"
    )


def test_unknown_provider_is_rejected(settings_env):
    """A typo'd provider is now a config-load error, not a model-call error.

    Gói P55 khôi phục `VisionProvider` về `Literal` (trước đó bị hạ xuống `str`
    trong lần gộp repo), nên `VISION_PROVIDER` không hợp lệ bị pydantic bắt ngay
    lúc `Settings()` dựng — fail-fast, không chờ tới lúc gọi model.
    """
    with pytest.raises(ValidationError, match="definitely-not-a-provider"):
        settings_env(VISION_PROVIDER="definitely-not-a-provider")
