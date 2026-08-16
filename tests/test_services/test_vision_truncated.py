"""Chạm trần token phải báo đúng tên, không được giả dạng lỗi JSON hỏng."""

from __future__ import annotations

import pytest

from src.services.vision.base import VisionTruncatedError, VisionUnavailableError
from src.services.vision.openai_compat import OpenAICompatibleClient


class _FakeClient(OpenAICompatibleClient):
    """Client giả: thay `_post` bằng một phản hồi dựng sẵn."""

    def __init__(self, body: dict) -> None:
        super().__init__("groq", "https://example.invalid/v1", "gsk_test")
        self._body = body

    def _post(self, payload: dict) -> dict:  # type: ignore[override]
        return self._body


def test_finish_reason_length_bao_dung_ma_loi() -> None:
    client = _FakeClient({"choices": [{"message": {"content": '{"items":[{"ten":"cha'}, "finish_reason": "length"}]})
    with pytest.raises(VisionTruncatedError) as loi:
        client.classify_text("chai nhua", [], "qwen/qwen3.6-27b")
    assert loi.value.code == "VISION-LENGTH"


def test_noi_dung_rong_bao_dung_ma_loi() -> None:
    """Model suy luận tiêu hết trần vào phần nghĩ rồi trả rỗng."""
    client = _FakeClient({"choices": [{"message": {"content": ""}, "finish_reason": "stop"}]})
    with pytest.raises(VisionTruncatedError) as loi:
        client.classify_text("chai nhua", [], "openai/gpt-oss-120b")
    assert loi.value.code == "VISION-EMPTY"


def test_van_la_mot_loai_vision_unavailable() -> None:
    """Lớp gọi cũ bắt VisionUnavailableError vẫn phải bắt được lỗi mới."""
    assert issubclass(VisionTruncatedError, VisionUnavailableError)
