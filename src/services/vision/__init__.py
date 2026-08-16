"""Lớp truy cập model vision, tách rời khỏi phần còn lại của hệ thống.

Mỗi tầng có nhà cung cấp riêng (xem ``src/config.py``), nên **luôn lấy client
theo tầng**::

    from src.services.vision import get_tier_model, get_vision_client

    client = get_vision_client("t1")
    result = client.classify_image(image_bytes, categories, get_tier_model("t1"))
"""

from __future__ import annotations

from src.config import ModelTier, get_settings
from src.services.vision.base import (
    PROMPT_VERSION,
    CategoryOption,
    Usage,
    VisionClient,
    VisionResult,
    VisionUnavailableError,
)
from src.services.vision.gemini import GeminiClient, build_gemini_client
from src.services.vision.local_clip import (
    classify_image_local,
)
from src.services.vision.local_clip import (
    is_loaded as local_model_loaded,
)
from src.services.vision.local_clip import (
    runtime_dang_dung as local_model_runtime,
)
from src.services.vision.local_clip import (
    warm_up as warm_up_local_model,
)
from src.services.vision.local_yolo import (
    is_loaded as yolo_loaded,
)
from src.services.vision.openai_compat import OpenAICompatibleClient, build_openai_compatible_client

__all__ = [
    "PROMPT_VERSION",
    "CategoryOption",
    "GeminiClient",
    "OpenAICompatibleClient",
    "Usage",
    "VisionClient",
    "VisionProviderError",
    "VisionResult",
    "VisionUnavailableError",
    "classify_image_local",
    "get_tier_model",
    "get_tier_models",
    "get_tier_provider",
    "get_vision_client",
    "get_vision_model",
    "local_model_loaded",
    "local_model_runtime",
    "provider_status",
    "warm_up_local_model",
    "yolo_loaded",
]

# Nhãn tiếng Việt của từng tầng, dùng cho trang Vận hành.
TIER_LABELS_VI: dict[str, str] = {
    "t1": "T1 — phân loại thường",
    "t2": "T2 — kiểm tra ca khó",
    "text": "Hướng dẫn (advise) + hỏi bằng chữ",
}


def build_client_for(provider: str) -> VisionClient:
    """Dựng client cho **một nhà cung cấp cụ thể**, không đọc tầng.

    Raises:
        VisionUnavailableError: khi provider là ``local_only`` (không có model
            đám mây nào để gọi) hoặc tên provider không hợp lệ.
    """
    if provider == "gemini":
        return build_gemini_client()
    if provider in {"openai", "openrouter", "nvidia", "deepseek", "groq", "mistral"}:
        return build_openai_compatible_client(provider)
    if provider == "local_only":
        raise VisionUnavailableError(
            "Đang chạy ở chế độ chỉ dùng model local, không gọi model đám mây.",
            code="VISION-LOCAL",
        )
    raise VisionUnavailableError(f"VISION_PROVIDER='{provider}' không hợp lệ.", code="VISION-400")


def get_vision_client(tier: ModelTier = "t1") -> VisionClient:
    """Trả về client của nhà cung cấp phụ trách ``tier``.

    Mỗi tầng có thể chạy trên một nhà cung cấp khác nhau (``VISION_PROVIDER_T1``
    / ``_T2`` / ``_TEXT``), nên **phải truyền tầng** thay vì dùng một client
    chung: hết quota ở T2 thì T1 vẫn phải sống.
    """
    return build_client_for(get_settings().resolve_provider(tier))


def get_tier_provider(tier: ModelTier = "t1") -> str:
    """Tên nhà cung cấp phụ trách một tầng."""
    return get_settings().resolve_provider(tier)


def get_tier_model(tier: ModelTier = "t1") -> str:
    """Tên model của một tầng, theo provider phụ trách tầng đó."""
    return get_settings().resolve_model_for(tier)


def get_tier_models() -> tuple[str, str, str]:
    """``(model_T1, model_T2, model_text)``. Lớp bọc cho chỗ cần cả ba cùng lúc."""
    return get_settings().resolve_models()


def provider_status() -> dict[str, object]:
    """Tóm tắt cấu hình model để hiện trên trang Vận hành.

    Trả về **bảng theo từng tầng** (``tiers``) vì các tầng có thể chạy trên ba
    nhà cung cấp khác nhau. Các khoá phẳng ``provider`` / ``model_t1`` … vẫn giữ
    cho hợp đồng API cũ ở ``FRONTEND_SPEC.md`` mục 7.

    Có key hay không là thông tin vận hành cần thiết; **giá trị key không bao
    giờ được trả ra ngoài**.
    """
    settings = get_settings()
    tiers: list[dict[str, object]] = []
    for tier in ("t1", "t2", "text"):
        provider = settings.resolve_provider(tier)  # type: ignore[arg-type]
        tiers.append(
            {
                "tier": tier,
                "label_vi": TIER_LABELS_VI[tier],
                "provider": provider,
                "model": settings.resolve_model_for(tier),  # type: ignore[arg-type]
                # ``local_only`` không cần key nên coi như đã đủ điều kiện chạy.
                "has_api_key": bool(settings.api_key_for(provider)) or provider == "local_only",
            }
        )

    t1, t2, text = settings.resolve_models()
    return {
        "provider": settings.vision_provider,
        "has_api_key": bool(settings.provider_api_key),
        "model_t1": t1,
        "model_t2": t2,
        "model_text": text,
        "tiers": tiers,
        # Đúng khi và chỉ khi mọi tầng đều gọi cùng một nhà cung cấp.
        "single_provider": len({str(t["provider"]) for t in tiers}) == 1,
        "local_model_enabled": settings.local_model_enabled,
        "local_model_name": settings.clip_model_name if settings.local_model_enabled else "",
        # "onnx" (bản nén, chạy được trên máy chủ free) · "torch" (bản đầy đủ,
        # máy dev) · "" (chưa nạp). Xem ADR-0007.
        "local_model_runtime": local_model_runtime(),
        "prompt_version": settings.prompt_version,
    }


class VisionProviderError(RuntimeError):
    """No usable Vision provider is configured."""


class _StubVisionModel:
    """Returns a canned prediction. **Never for production.**

    Exists so the LED feedback paths (ok / warning / hazard) can be exercised
    end-to-end without an API key — see iot/docs/testing-without-hardware.md.
    """

    def __init__(self, label: str, confidence: float) -> None:
        self._label = label
        self._confidence = confidence

    async def ainvoke(self, _messages):
        import logging

        log = logging.getLogger(__name__)
        log.warning(
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
    """Return a LangChain chat model capable of image input."""
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

        extra = {}
        if settings.vision_base_url:
            extra["base_url"] = settings.vision_base_url

        return ChatOpenAI(
            model=settings.vision_model_name,
            api_key=settings.openai_api_key,
            temperature=0,
            **extra,
        )

    raise VisionProviderError(f"Unsupported vision provider: {provider!r}")

