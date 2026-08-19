"""Tự kiểm Storage (``luu_tru.kiem_tra``) — gói P52.

``/ops/metrics`` giờ phơi trạng thái Storage. Mục tiêu của ``kiem_tra``: thay vì
lỗi im lặng rơi về đĩa, mở /ops là thấy ngay Storage đang nghĩ gì (404=URL sai,
401/403=khoá sai, tắt cờ…). Không test nào chạm mạng: nhánh tắt thoát sớm ở
``_cau_hinh``, nhánh lỗi HTTP dùng lớp HTTP giả theo đúng khuôn
``test_luu_tru.py``.
"""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest

from src.config import reset_settings_cache
from src.services import luu_tru


@pytest.fixture(autouse=True)
def _don_trang_thai(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Xoá biến Storage khỏi môi trường để test không bao giờ đụng mạng thật."""
    monkeypatch.delenv("STORAGE_ENABLED", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_BUCKET", raising=False)
    reset_settings_cache()
    yield
    reset_settings_cache()


class _PhanHoiGia:
    def __init__(self, ma: int) -> None:
        self.status_code = ma


class _KhachGia:
    """Thay cho httpx.Client — không chạm mạng, ghi lại thứ đã gọi."""

    def __init__(self, ma_ghi: int = 200, ma_doc: int = 200) -> None:
        self.ma_ghi = ma_ghi
        self.ma_doc = ma_doc
        self.cac_goi: list[str] = []

    def __enter__(self) -> _KhachGia:
        return self

    def __exit__(self, *args) -> None:
        return None

    def post(self, url: str, *, headers: dict, content: bytes) -> _PhanHoiGia:
        self.cac_goi.append("POST")
        return _PhanHoiGia(self.ma_ghi)

    def get(self, url: str, *, headers: dict) -> _PhanHoiGia:
        self.cac_goi.append("GET")
        return _PhanHoiGia(self.ma_doc)

    def delete(self, url: str, *, headers: dict) -> _PhanHoiGia:
        self.cac_goi.append("DELETE")
        return _PhanHoiGia(200)


def _gia_http(monkeypatch: pytest.MonkeyPatch, khach: _KhachGia) -> _KhachGia:
    gia = type(
        "GiaHttpx",
        (),
        {
            "Client": lambda *a, **k: khach,
            "HTTPError": httpx.HTTPError,
        },
    )
    monkeypatch.setattr(luu_tru, "httpx", gia)
    return khach


def test_mac_dinh_tat_thi_khong_dung_mang(monkeypatch: pytest.MonkeyPatch) -> None:
    """``storage_enabled=False`` (mặc định) → thoát sớm, không gọi mạng một lần nào."""
    khach = _gia_http(monkeypatch, _KhachGia())

    ket = luu_tru.kiem_tra()

    assert ket["enabled"] is False
    assert ket["ok"] is False
    assert "tắt" in str(ket["chi_tiet"])
    assert khach.cac_goi == [], "Cờ tắt thì không được gọi mạng một lần nào"


def test_cau_hinh_none_thi_bao_tat_du_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Chốt chặn nhánh tắt: ``_cau_hinh`` trả ``None`` thì báo thiếu, kể cả cờ bật."""
    monkeypatch.setenv("STORAGE_ENABLED", "true")
    reset_settings_cache()
    khach = _gia_http(monkeypatch, _KhachGia())
    monkeypatch.setattr(luu_tru, "_cau_hinh", lambda: None)

    ket = luu_tru.kiem_tra()

    assert ket["enabled"] is True, "Cờ bật nhưng thiếu URL/khoá → vẫn phơi enabled=True"
    assert ket["ok"] is False
    assert "tắt" in str(ket["chi_tiet"])
    assert khach.cac_goi == []


def test_ghi_loi_http_thi_bao_dung_ma(monkeypatch: pytest.MonkeyPatch) -> None:
    """Storage trả 404 khi ghi → ``ok=False`` kèm mã HTTP để chẩn URL/khoá/bucket."""
    monkeypatch.setattr(
        luu_tru,
        "_cau_hinh",
        lambda: ("https://supabase.example", "khoa-bi-mat", "greenbin"),
    )
    khach = _gia_http(monkeypatch, _KhachGia(ma_ghi=404))

    ket = luu_tru.kiem_tra()

    assert ket["ok"] is False
    assert "ghi lỗi HTTP 404" in str(ket["chi_tiet"])
    assert khach.cac_goi == ["POST"], "Lỗi ghi phải dừng ngay, không gọi đọc/xoá"
