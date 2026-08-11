"""Test hình đường đi thật (gói P26) — KHÔNG test nào chạm mạng thật.

Thay ``httpx`` bằng bản giả y như ``test_duong_di_that.py``: đếm số lần gọi,
bắt URL, trả dữ liệu do test tự quyết. Trọng tâm là chiều ``[lng, lat]`` của
GeoJSON phải được đảo về ``(lat, lng)`` — sai chiều thì đường vẽ ra nằm ở
Somalia mà không có lỗi nào.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from src.config import reset_settings_cache
from src.services import duong_di_that
from src.services.duong_di_that import hinh_duong_di


@pytest.fixture(autouse=True)
def _xoam_cache_cau_hinh() -> Iterator[None]:
    """Cấu hình đọc qua ``lru_cache`` nên phải xoá cache quanh mỗi test."""
    reset_settings_cache()
    yield
    reset_settings_cache()


def _bat_co(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROUTE_REAL_DISTANCE", "true")
    reset_settings_cache()


def _tat_co(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROUTE_REAL_DISTANCE", "false")
    reset_settings_cache()


def _gia_http(
    monkeypatch: pytest.MonkeyPatch,
    *,
    du_lieu: dict | None = None,
    loi: Exception | None = None,
) -> tuple[list[int], list[str]]:
    """Thay ``httpx`` của module bằng bản giả; trả về ``(số lần gọi, danh sách URL)``."""

    so_lan: list[int] = [0]
    cac_url: list[str] = []

    class _PhanHoi:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return du_lieu or {}

    class _Khach:
        def __init__(self, timeout: float) -> None:
            pass

        def __enter__(self) -> _Khach:
            return self

        def __exit__(self, *args: object) -> bool:
            return False

        def get(self, url: str) -> _PhanHoi:
            so_lan[0] += 1
            cac_url.append(url)
            if loi is not None:
                raise loi
            return _PhanHoi()

    class _Gia:
        Client = _Khach

    monkeypatch.setattr(duong_di_that, "httpx", _Gia)
    return so_lan, cac_url


HAI_DIEM = [(21.0278, 105.8342), (21.0312, 105.8507)]

_HINH_GEOJSON = {"routes": [{"geometry": {"coordinates": [[105.85, 21.03], [105.86, 21.04]]}}]}


def test_co_tat_thi_khong_goi_mang(monkeypatch: pytest.MonkeyPatch) -> None:
    _tat_co(monkeypatch)
    so_lan, _ = _gia_http(monkeypatch)

    ket_qua = hinh_duong_di(HAI_DIEM)

    assert ket_qua is None
    assert so_lan[0] == 0, "Cờ tắt thì không được gọi mạng một lần nào"


def test_doi_dung_lng_lat_trong_url(monkeypatch: pytest.MonkeyPatch) -> None:
    _bat_co(monkeypatch)
    so_lan, cac_url = _gia_http(monkeypatch, du_lieu=_HINH_GEOJSON)

    hinh_duong_di(HAI_DIEM)

    assert so_lan[0] == 1
    assert "105.8342,21.0278" in cac_url[0], (
        "Điểm (21.0278, 105.8342) phải vào URL dạng '105.8342,21.0278' — lng trước, lat sau"
    )
    assert "/route/v1/driving/" in cac_url[0], "Phải gọi endpoint /route chứ không phải /table"


def test_doc_geojson_va_dao_ve_lat_lng(monkeypatch: pytest.MonkeyPatch) -> None:
    """Chốt chặn chính: GeoJSON trả [lng, lat], hàm phải trả (lat, lng)."""
    _bat_co(monkeypatch)
    _gia_http(monkeypatch, du_lieu=_HINH_GEOJSON)

    ket_qua = hinh_duong_di(HAI_DIEM)

    assert ket_qua is not None
    assert ket_qua[0] == (21.03, 105.85), "Phải đảo [lng, lat] về (lat, lng)"
    assert ket_qua[1] == (21.04, 105.86)


def test_dich_vu_hong_thi_tra_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _bat_co(monkeypatch)
    so_lan, _ = _gia_http(monkeypatch, loi=OSError("mạng chập chờn"))

    ket_qua = hinh_duong_di(HAI_DIEM)

    assert ket_qua is None, "Hỏng thì rơi về nét đứt, không ném ngoại lệ"
    assert so_lan[0] == 1


def test_qua_han_thi_tra_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _bat_co(monkeypatch)
    _gia_http(monkeypatch, loi=TimeoutError("quá hạn"))

    assert hinh_duong_di(HAI_DIEM) is None


def test_du_lieu_sai_hinh_dang_thi_tra_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _bat_co(monkeypatch)

    _gia_http(monkeypatch, du_lieu={})  # thiếu routes
    assert hinh_duong_di(HAI_DIEM) is None

    _gia_http(monkeypatch, du_lieu={"routes": []})  # routes rỗng
    assert hinh_duong_di(HAI_DIEM) is None

    _gia_http(monkeypatch, du_lieu={"routes": [{"geometry": {}}]})  # thiếu coordinates
    assert hinh_duong_di(HAI_DIEM) is None

    _gia_http(monkeypatch, du_lieu={"routes": [{"geometry": {"coordinates": []}}]})  # geometry rỗng
    assert hinh_duong_di(HAI_DIEM) is None


def test_duoi_hai_diem_thi_tra_none_va_khong_goi_mang(monkeypatch: pytest.MonkeyPatch) -> None:
    _bat_co(monkeypatch)
    so_lan, _ = _gia_http(monkeypatch)

    ket_qua = hinh_duong_di([(21.0278, 105.8342)])

    assert ket_qua is None
    assert so_lan[0] == 0, "Một điểm thì không có đường nào để vẽ, không gọi mạng"
