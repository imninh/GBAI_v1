"""Vision model routing.

The single place a Vision provider is selected. Devices never call a provider
directly and never hold a provider key (spec §8, §26) — the key lives in backend
settings only.
"""

from __future__ import annotations

import logging

from src.config import get_settings

logger = logging.getLogger(__name__)


class VisionProviderError(RuntimeError):
    """No usable Vision provider is configured."""


class _StubVisionModel:
    """Returns a canned prediction. **Never for production.**

    Exists so the LED feedback paths (ok / warning / hazard) can be exercised
    end-to-end without an API key — see iot/docs/testing-without-hardware.md.
    Reached only when ``VISION_PROVIDER=stub`` is set explicitly, and it shouts
    about itself every single call so it cannot be mistaken for a real result.
    """

    def __init__(self, label: str, confidence: float) -> None:
        self._label = label
        self._confidence = confidence

    async def ainvoke(self, _messages):
        logger.warning(
            "STUB VISION PROVIDER — returning canned label %r at confidence %.2f. "
            "No image was analysed.",
            self._label,
            self._confidence,
        )

        class _Reply:
            content = (
                f'{{"label": "{self._label}", "confidence": {self._confidence}}}'
            )

        return _Reply()


def get_vision_model():
    """Return a LangChain chat model capable of image input.

    Only OpenAI is wired up: ``langchain-gemini`` is installed in this
    environment but ships as an empty stub with no chat class, so routing to it
    would fail at call time rather than here. Additional providers slot in as
    extra branches without touching callers.
    """
    settings = get_settings()
    provider = settings.vision_provider.strip().lower()

    if provider == "stub":
        return _StubVisionModel(
            settings.stub_vision_label, settings.stub_vision_confidence
        )

    if provider == "openai":
        if not settings.openai_api_key:
            raise VisionProviderError("OPENAI_API_KEY is not configured")
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.vision_model_name,
            api_key=settings.openai_api_key,
            temperature=0,  # classification, not creative writing
        )

    raise VisionProviderError(f"Unsupported vision provider: {provider!r}")
