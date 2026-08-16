"""Giới hạn bùng nổ của 2-opt trên dữ liệu lớn (gói P35).

Bộ GIS Hà Nội có 60 thùng, mà ``sap_thu_tu`` là O(n³) mỗi vòng nhân thêm số
điểm xuất phát — tuyến 60 điểm từng treo request hàng chục giây. Gói này cắt số
*điểm xuất phát* về 1 trên ngưỡng ``NGUONG_NHIEU_DIEM``, KHÔNG cắt thuật toán:
2-opt vẫn phải chạy, và hai lời hứa của ``sap_thu_tu`` vẫn giữ — kết quả không
bao giờ tệ hơn thứ tự đưa vào, và cùng đầu vào cho cùng đầu ra.

Dùng điểm phẳng Euclid đúng như ``test_toi_uu_tuyen.py``. Không test nào chạm
mạng, không cần CSDL.
"""

from __future__ import annotations

import random
import time
from math import sqrt

import pytest

from src.services import toi_uu_tuyen as module
from src.services.toi_uu_tuyen import do_dai, nearest_neighbour, sap_thu_tu


def _euclid(a: tuple[float, float], b: tuple[float, float]) -> float:
    return sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


def _bo_diem(n: int, seed: int = 7) -> list[tuple[float, float]]:
    rng = random.Random(seed)
    return [(rng.uniform(0, 100), rng.uniform(0, 100)) for _ in range(n)]


def _dem_nearest_neighbour(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    nguyen_goc = module.nearest_neighbour
    so_lan = [0]

    def _dem(diem, khoang_cach):
        so_lan[0] += 1
        return nguyen_goc(diem, khoang_cach)

    monkeypatch.setattr(module, "nearest_neighbour", _dem)
    return so_lan


def test_it_diem_van_thu_nhieu_diem_dau(monkeypatch: pytest.MonkeyPatch) -> None:
    """10 điểm (dưới ngưỡng) → vẫn chạy đủ `SO_DIEM_DAU_TOI_DA` điểm xuất phát."""
    so_lan = _dem_nearest_neighbour(monkeypatch)

    sap_thu_tu(_bo_diem(10), _euclid)

    assert so_lan[0] == module.SO_DIEM_DAU_TOI_DA


def test_nhieu_diem_thi_chi_mot_diem_dau(monkeypatch: pytest.MonkeyPatch) -> None:
    """60 điểm (trên ngưỡng) → đúng 1 lần gọi nearest-neighbour."""
    so_lan = _dem_nearest_neighbour(monkeypatch)

    sap_thu_tu(_bo_diem(60), _euclid)

    assert so_lan[0] == 1


def test_ket_qua_khong_bao_gio_te_hon_dau_vao() -> None:
    """Chốt chặn chính. Docstring của `sap_thu_tu` hứa: "không bao giờ dài hơn
    thứ tự đưa vào" — thứ tự gốc được đưa vào cuộc thi làm đương kim ngay từ
    đầu. Với ngưỡng mới, bản `k = 0` có thể tệ hơn thứ tự gốc, nhưng `goc` vẫn
    giữ làm đương kim nên lời hứa không được phép vỡ."""
    rng = random.Random(20260812)
    for _ in range(200):
        n = rng.randrange(5, 61)
        diem = [(rng.uniform(0, 100), rng.uniform(0, 100)) for _ in range(n)]
        ket_qua = sap_thu_tu(diem, _euclid)
        assert do_dai(ket_qua, _euclid) <= do_dai(diem, _euclid) + 1e-9


def test_van_xac_dinh() -> None:
    """Cùng đầu vào chạy hai lần cho kết quả y hệt — cả dưới lẫn trên ngưỡng."""
    for n in (10, 40):
        diem = _bo_diem(n)
        lan_dau = sap_thu_tu(diem, _euclid)
        lan_sau = sap_thu_tu(diem, _euclid)
        assert lan_dau == lan_sau


def test_khong_mat_phan_tu() -> None:
    """Đầu ra là hoán vị của đầu vào — đủ số, không trùng, hai phía ngưỡng."""
    for n in (10, 60):
        diem = _bo_diem(n)
        ket_qua = sap_thu_tu(diem, _euclid)
        assert len(ket_qua) == len(diem)
        assert set(ket_qua) == set(diem)


def test_60_diem_chay_duoi_mot_giay() -> None:
    """Ngưỡng rộng có chủ đích — máy CI chậm hơn máy dev. Mục đích là bắt hồi
    quy bậc-độ-lớn (một lần 2-opt thôi), không phải đo hiệu năng chính xác."""
    diem = _bo_diem(60)
    bat_dau = time.perf_counter()
    sap_thu_tu(diem, _euclid)
    thoi_gian = time.perf_counter() - bat_dau
    assert thoi_gian < 1.0


def test_hai_opt_van_duoc_chay_o_tuyen_lon() -> None:
    """60 điểm: kết quả ngắn hơn bản chỉ nearest-neighbour → 2-opt vẫn chạy
    chứ không bị cắt cùng với số điểm xuất phát."""
    diem = _bo_diem(60)
    ket_qua = sap_thu_tu(diem, _euclid)
    chi_nn = nearest_neighbour(list(diem), _euclid)
    assert do_dai(ket_qua, _euclid) < do_dai(chi_nn, _euclid)
