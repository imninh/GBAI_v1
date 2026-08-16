"""Test khoảng cách đường đi thật (gói G3) — KHÔNG test nào chạm mạng thật.

Thay ``httpx`` bằng một bản giả: đếm số lần gọi, bắt URL, và trả về dữ liệu do
test tự quyết — đúng luật "test không bao giờ gọi API thật" của cả repo.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from src.config import reset_settings_cache
from src.services import duong_di_that
from src.services.duong_di_that import ma_tran_km


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
        def __init__(self, timeout: float = 0, *args: object, **kwargs: object) -> None:
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


def test_co_tat_thi_khong_goi_mang(monkeypatch: pytest.MonkeyPatch) -> None:
    _tat_co(monkeypatch)
    so_lan, _ = _gia_http(monkeypatch)

    ket_qua = ma_tran_km(HAI_DIEM)

    assert ket_qua is None
    assert so_lan[0] == 0, "Cờ tắt thì không được gọi mạng một lần nào"


def test_toa_do_di_vao_url_dung_thu_tu_lng_lat(monkeypatch: pytest.MonkeyPatch) -> None:
    """Chốt chặn quan trọng nhất: OSRM cần ``lng,lat``, không phải ``lat,lng``."""
    _bat_co(monkeypatch)
    so_lan, cac_url = _gia_http(monkeypatch, du_lieu={"distances": [[0, 1], [1, 0]]})

    ma_tran_km(HAI_DIEM)

    assert so_lan[0] == 1
    assert "105.8342,21.0278" in cac_url[0], (
        "Điểm (21.0278, 105.8342) phải vào URL dạng '105.8342,21.0278' — lng trước, lat sau"
    )


def test_doi_met_sang_km(monkeypatch: pytest.MonkeyPatch) -> None:
    _bat_co(monkeypatch)
    _gia_http(monkeypatch, du_lieu={"distances": [[0, 1500], [1500, 0]]})

    ket_qua = ma_tran_km(HAI_DIEM)

    assert ket_qua == [[0.0, 1.5], [1.5, 0.0]]


def test_dich_vu_hong_thi_tra_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _bat_co(monkeypatch)
    so_lan, _ = _gia_http(monkeypatch, loi=OSError("mạng chập chờn"))

    ket_qua = ma_tran_km(HAI_DIEM)

    assert ket_qua is None, "Hỏng thì rơi về haversine, không ném ngoại lệ"
    assert so_lan[0] == 1


def test_qua_han_thi_tra_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _bat_co(monkeypatch)
    _gia_http(monkeypatch, loi=TimeoutError("quá 3 giây"))

    ket_qua = ma_tran_km(HAI_DIEM)

    assert ket_qua is None


def test_du_lieu_tra_ve_sai_hinh_dang_thi_tra_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _bat_co(monkeypatch)

    _gia_http(monkeypatch, du_lieu={})  # thiếu khoá distances
    assert ma_tran_km(HAI_DIEM) is None

    _gia_http(monkeypatch, du_lieu={"distances": [[0, 1]]})  # ma trận không vuông
    assert ma_tran_km(HAI_DIEM) is None


def test_duoi_hai_diem_thi_tra_none_va_khong_goi_mang(monkeypatch: pytest.MonkeyPatch) -> None:
    _bat_co(monkeypatch)
    so_lan, _ = _gia_http(monkeypatch)

    ket_qua = ma_tran_km([(21.0278, 105.8342)])

    assert ket_qua is None
    assert so_lan[0] == 0, "Một điểm thì không có gì để đo, không gọi mạng"


def test_ma_tran_osrm_tra_ca_distance_va_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    _bat_co(monkeypatch)
    _gia_http(
        monkeypatch,
        du_lieu={
            "distances": [[0, 2000], [2000, 0]],
            "durations": [[0, 180], [180, 0]],
        },
    )

    kq = duong_di_that.ma_tran_osrm(HAI_DIEM)

    assert kq is not None
    assert kq.distances_km == [[0.0, 2.0], [2.0, 0.0]]
    assert kq.durations_s == [[0.0, 180.0], [180.0, 0.0]]


def test_ham_do_thoi_gian_tra_dung_gia_tri() -> None:
    durations = [[0.0, 120.0], [120.0, 0.0]]
    chi_so = {"diem_1": 0, "diem_2": 1}
    fn = duong_di_that.ham_do_thoi_gian_tu_ma_tran(durations, chi_so)

    class Diem:
        def __init__(self, diem_id: str):
            self.diem_id = diem_id

    assert fn(Diem("diem_1"), Diem("diem_2")) == 120.0
    assert fn(Diem("diem_1"), Diem("diem_khong_co")) is None


def test_snap_gps_voi_tracepoints(monkeypatch: pytest.MonkeyPatch) -> None:
    _bat_co(monkeypatch)
    _gia_http(
        monkeypatch,
        du_lieu={
            "tracepoints": [
                {"location": [105.8345, 21.0280]},
                {"location": [105.8510, 21.0315]},
            ]
        },
    )

    raw_points = [(21.0278, 105.8342), (21.0312, 105.8507)]
    snapped = duong_di_that.snap_gps(raw_points, timestamps=[1000, 1005])

    assert snapped is not None
    assert len(snapped) == 2
    assert snapped[0] == (21.0280, 105.8345)
    assert snapped[1] == (21.0315, 105.8510)


def test_snap_gps_co_tat_tra_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _tat_co(monkeypatch)
    so_lan, _ = _gia_http(monkeypatch)

    raw_points = [(21.0278, 105.8342), (21.0312, 105.8507)]
    assert duong_di_that.snap_gps(raw_points) is None
    assert so_lan[0] == 0


def test_snap_gps_loi_mang_fallback_raw(monkeypatch: pytest.MonkeyPatch) -> None:
    _bat_co(monkeypatch)
    _gia_http(monkeypatch, loi=OSError("disconnect"))

    raw_points = [(21.0278, 105.8342), (21.0312, 105.8507)]
    snapped = duong_di_that.snap_gps(raw_points)

    assert snapped == raw_points, "Hỏng thì fallback toạ độ thô ban đầu, không mất dữ liệu"


def test_dan_duong_co_tat_tra_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _tat_co(monkeypatch)
    so_lan, _ = _gia_http(monkeypatch)

    res = duong_di_that.dan_duong((21.0278, 105.8342), (21.0312, 105.8507))
    assert res is None
    assert so_lan[0] == 0


def test_dan_duong_thanh_cong(monkeypatch: pytest.MonkeyPatch) -> None:
    _bat_co(monkeypatch)
    so_lan, cac_url = _gia_http(
        monkeypatch,
        du_lieu={
            "routes": [
                {
                    "distance": 1850.0,
                    "duration": 240.0,
                    "geometry": {
                        "coordinates": [
                            [105.8342, 21.0278],
                            [105.8400, 21.0290],
                            [105.8507, 21.0312],
                        ]
                    },
                }
            ]
        },
    )

    res = duong_di_that.dan_duong((21.0278, 105.8342), (21.0312, 105.8507))
    assert res is not None
    assert res.distance_km == 1.85
    assert res.duration_minutes == 4.0
    assert len(res.polyline) == 3
    assert res.polyline[0] == (21.0278, 105.8342)
    assert res.polyline[-1] == (21.0312, 105.8507)
    assert "105.8342,21.0278;105.8507,21.0312" in cac_url[0]


def test_dan_duong_loi_mang_tra_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _bat_co(monkeypatch)
    _gia_http(monkeypatch, loi=OSError("network timeout"))

    res = duong_di_that.dan_duong((21.0278, 105.8342), (21.0312, 105.8507))
    assert res is None

