"""Groq reasoning phải tắt suy nghĩ và bỏ JSON mode của Groq, provider khác thì không.

Groq chạy model suy luận (qwen3.x): đo thật 16/08/2026 trên qwen/qwen3.6-27b,
model tiêu HẾT 2000 token đầu ra vào phần suy nghĩ rồi trả nội dung RỖNG
(finish_reason "length"); kèm `response_format` thì Groq kiểm JSON trên chuỗi
rỗng và trả HTTP 400 `json_validate_failed`.

`reasoning_effort: "none"` tắt hẳn suy nghĩ; bỏ `response_format` để phần kiểm
JSON do `parse_model_json` của mình làm (chạm trần thì báo VISION-LENGTH).
Giữ `reasoning_format: "hidden"` cho groq. Các tham số này là của riêng Groq.
"""

from __future__ import annotations

from src.services.vision.openai_compat import OpenAICompatibleClient


class _GhiPayloadClient(OpenAICompatibleClient):
    """Client ghi lại payload vừa gửi, không gọi mạng thật."""

    def __init__(self, provider: str) -> None:
        super().__init__(provider, "https://example.invalid/v1", "key-gia")
        self.payload: dict = {}

    def _post(self, payload: dict) -> dict:  # type: ignore[override]
        self.payload = payload
        return {"choices": [{"message": {"content": '{"items":[]}', "finish_reason": "stop"}}]}


def test_groq_gui_reasoning_format_hidden() -> None:
    """Groq là model reasoning nên phải kèm `reasoning_format: "hidden"`."""
    client = _GhiPayloadClient("groq")
    client.classify_text("chai nhua", [], "qwen/qwen3.6-27b")
    assert client.payload.get("reasoning_format") == "hidden"


def test_groq_tat_suy_nghi_va_bo_json_mode() -> None:
    """Groq phải gửi `reasoning_effort: none` và KHÔNG có `response_format`."""
    client = _GhiPayloadClient("groq")
    client.classify_text("chai nhua", [], "qwen/qwen3.6-27b")
    assert client.payload.get("reasoning_effort") == "none"
    assert "response_format" not in client.payload


def test_nvidia_khong_gui_tham_so_reasoning_cua_groq() -> None:
    """NVIDIA không phải reasoning của Groq — không gửi hai tham số kia."""
    client = _GhiPayloadClient("nvidia")
    client.classify_text("chai nhua", [], "llama-3.2-90b-vision")
    assert "reasoning_format" not in client.payload
    assert "reasoning_effort" not in client.payload


def test_openai_khong_gui_tham_so_reasoning_cua_groq() -> None:
    """OpenAI/OpenRouter cũng không dùng các tham số này."""
    client = _GhiPayloadClient("openrouter")
    client.classify_text("chai nhua", [], "openai/gpt-oss-120b")
    assert "reasoning_format" not in client.payload
    assert "reasoning_effort" not in client.payload


def test_response_format_van_con_cho_provider_khac() -> None:
    """JSON mode vẫn bật cho mọi provider KHÔNG phải groq."""
    for provider in ("nvidia", "openrouter", "openai", "gemini"):
        client = _GhiPayloadClient(provider)
        client.classify_text("chai nhua", [], "model-x")
        assert client.payload.get("response_format") == {"type": "json_object"}
