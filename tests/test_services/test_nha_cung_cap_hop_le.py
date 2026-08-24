"""Gói P55 — mọi tên trong `VisionProvider` phải là nhà cung cấp THẬT.

Trước lần gộp repo, `VisionProvider` là một `Literal` liệt kê đủ tên hợp lệ; bên
kia hạ xuống `str` để lọt `"stub"` của họ, hậu quả là **gõ sai tên provider không
ai phát hiện** cho tới lúc gọi model và nhận VISION-400. Test này khoá lại danh
sách, để gõ sai tên là vỡ ngay lúc chạy chứ không phải lúc chấm.
"""

from __future__ import annotations

from typing import get_args

import pytest

from src.config import PROVIDER_DEFAULT_MODELS, VisionProvider
from src.services.vision import build_client_for
from src.services.vision.base import VisionUnavailableError

# `stub` là nhà cung cấp của đường IoT (`get_vision_model`), KHÔNG phải của
# `build_client_for` — tên này nằm trong Literal theo yêu cầu gói P55 (đường
# `get_vision_model` phục vụ nó, `.env.example` cũng khai `VISION_PROVIDER=stub`),
# nhưng `build_client_for("stub")` rơi vào nhánh "không hợp lệ" (VISION-400).
# Đây đúng là "cái bẫy khác" đặc tả P55 cảnh báo: đừng thêm nhánh, hãy báo lại.
STUB = "stub"


def _cac_ten_trong_literal() -> list[str]:
    return list(get_args(VisionProvider))


def test_moi_ten_trong_literal_duoc_build_client_for_chap_nhan_hoac_co_ma_ro() -> None:
    """Mọi tên trong Literal phải là provider thật: `build_client_for` dựng được
    client, hoặc ném lỗi có mã RIÊNG (local_only → VISION-LOCAL). Không tên nào
    được rơi vào nhánh "không hợp lệ" (VISION-400) — trừ `stub`, đường riêng của
    `get_vision_model` đã kiểm ở test dưới."""
    for ten in _cac_ten_trong_literal():
        if ten == STUB:
            continue
        try:
            build_client_for(ten)
        except VisionUnavailableError as loi:
            assert loi.code != "VISION-400", (
                f"'{ten}' rơi vào nhánh 'không hợp lệ' (VISION-400) — gõ sai tên "
                "provider sẽ không ai phát hiện"
            )


def test_stub_la_provider_that_cua_duong_get_vision_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`stub` hợp lệ vì `get_vision_model` phục vụ nó — không phải `build_client_for`.

    Đây là "cái bẫy khác" mà đặc tả P55 cảnh báo: tên nằm trong Literal nhưng
    `build_client_for` không nhận. Không tự thêm nhánh vào `build_client_for` —
    báo cáo ghi rõ để người duyệt quyết.
    """
    assert STUB in _cac_ten_trong_literal()

    from src.config import get_settings
    from src.services.vision import get_vision_model

    # `get_vision_model` hiểu `stub` (đường IoT) — khai vào Settings rồi dựng thử.
    monkeypatch.setenv("VISION_PROVIDER", STUB)
    get_settings.cache_clear()
    try:
        model = get_vision_model()
        assert model is not None
    finally:
        get_settings.cache_clear()


def test_ten_bia_khong_thuoc_literal() -> None:
    """Tên bịa ('khong-ton-tai') không được nằm trong Literal."""
    assert "khong-ton-tai" not in _cac_ten_trong_literal()


def test_provider_default_models_khong_co_khoa_ngoai_literal() -> None:
    """Mọi khoá của `PROVIDER_DEFAULT_MODELS` phải nằm trong Literal."""
    cac_khoa = set(PROVIDER_DEFAULT_MODELS)
    ngoai = cac_khoa - set(_cac_ten_trong_literal())
    assert ngoai == set(), f"Khoá ngoài Literal: {sorted(ngoai)}"


@pytest.mark.parametrize("ten", ["gemini", "groq", "openai", "openrouter", "nvidia", "deepseek", "mistral"])
def test_cac_provider_openai_compatible_va_gemini_duoc_chap_nhan(ten: str) -> None:
    """Các tên mà `build_client_for` dựng được client phải nằm trong Literal."""
    assert ten in _cac_ten_trong_literal()
    client = build_client_for(ten)
    assert client is not None


def test_local_only_nam_trong_literal_va_co_ma_ro() -> None:
    """`local_only` nằm trong Literal và `build_client_for` ném lỗi có mã riêng."""
    assert "local_only" in _cac_ten_trong_literal()
    with pytest.raises(VisionUnavailableError) as loi:
        build_client_for("local_only")
    assert loi.value.code == "VISION-LOCAL"
    assert loi.value.code != "VISION-400"
