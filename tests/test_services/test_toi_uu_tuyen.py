"""Tối ưu thứ tự ghé điểm dừng — nearest-neighbour + 2-opt.

Dùng điểm phẳng ``(x, y)`` và khoảng cách Euclid cho dễ đọc: module không biết
gì về haversine, đo bằng gì cũng được. Không cần CSDL, không cần fixture.
"""

from __future__ import annotations

from math import sqrt

from src.services import toi_uu_tuyen as module
from src.services.toi_uu_tuyen import do_dai, hai_opt, nearest_neighbour, sap_thu_tu


def _euclid(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Khoảng cách Euclid giữa hai điểm phẳng."""
    return sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


def _manhattan(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Khoảng cách Manhattan giữa hai điểm phẳng."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


# Tám điểm cố định, viết cứng toạ độ — không dùng random để kết quả ổn định.
DIEM_COT_DINH = [
    (0.0, 0.0),
    (3.0, 1.0),
    (1.0, 4.0),
    (6.0, 2.0),
    (2.0, 7.0),
    (8.0, 5.0),
    (4.0, 9.0),
    (7.0, 8.0),
]


def test_danh_sach_rong_va_mot_diem_tra_nguyen() -> None:
    assert sap_thu_tu([], _euclid) == []
    mot_diem = [(1.0, 2.0)]
    assert sap_thu_tu(mot_diem, _euclid) == mot_diem


def test_hai_diem_giu_nguyen_thu_tu() -> None:
    hai_diem = [(0.0, 0.0), (5.0, 5.0)]
    assert sap_thu_tu(hai_diem, _euclid) == hai_diem
    assert nearest_neighbour(hai_diem, _euclid) == hai_diem
    assert hai_opt(hai_diem, _euclid) == hai_diem


def test_khong_mat_va_khong_nhan_doi_diem_nao() -> None:
    ket_qua = sap_thu_tu(DIEM_COT_DINH, _euclid)
    assert len(ket_qua) == len(DIEM_COT_DINH)
    assert set(ket_qua) == set(DIEM_COT_DINH)


def test_khong_bao_gio_dai_hon_thu_tu_ban_dau() -> None:
    ban_dau = DIEM_COT_DINH
    ket_qua = sap_thu_tu(ban_dau, _euclid)
    assert do_dai(ket_qua, _euclid) <= do_dai(ban_dau, _euclid)


def test_hai_opt_go_duoc_duong_cheo() -> None:
    """Đi men theo cạnh hình vuông (tổng 3.0), không đi cắt chéo (3,414)."""
    cat_cheo = [(0.0, 0.0), (1.0, 1.0), (0.0, 1.0), (1.0, 0.0)]
    ket_qua = hai_opt(cat_cheo, _euclid)
    assert abs(do_dai(ket_qua, _euclid) - 3.0) < 1e-9
    assert set(ket_qua) == set(cat_cheo)


def test_nearest_neighbour_di_theo_diem_gan_nhat() -> None:
    xao_tron = [(0.0, 0.0), (3.0, 0.0), (1.0, 0.0), (2.0, 0.0)]
    assert nearest_neighbour(xao_tron, _euclid) == [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0)]


def test_ket_qua_xac_dinh_chay_hai_lan_nhu_nhau() -> None:
    lan_dau = sap_thu_tu(DIEM_COT_DINH, _euclid)
    lan_sau = sap_thu_tu(DIEM_COT_DINH, _euclid)
    assert lan_dau == lan_sau


def test_diem_trung_cho_thi_dung_canh_nhau() -> None:
    """Ba điểm cùng (0,0) phải đứng liền nhau, không bị chen bởi điểm (5,5)."""
    danh_sach = [(0.0, 0.0), (5.0, 5.0), (0.0, 0.0), (0.0, 0.0), (5.0, 5.0)]
    ket_qua = sap_thu_tu(danh_sach, _euclid)
    vi_tri_goc = [i for i, diem in enumerate(ket_qua) if diem == (0.0, 0.0)]
    assert len(vi_tri_goc) == 3
    assert vi_tri_goc == list(range(vi_tri_goc[0], vi_tri_goc[0] + 3))


def test_thu_nhieu_diem_dau_cho_ket_qua_ngan_hon() -> None:
    """Thả điểm đầu cho kết quả ngắn hơn hẳn bản khóa từ phần tử 0.

    Các điểm thẳng hàng, xáo để phần tử đầu nằm giữa hàng: khởi hành từ giữa thì
    luôn phải quay đầu về phía còn lại, trong khi khởi hành từ đầu hàng đi thẳng
    một mạch. ``sap_thu_tu`` thử cả hai đầu nên ngắn hơn hẳn.
    """
    danh_sach = [(2.0, 0.0), (0.0, 0.0), (1.0, 0.0), (3.0, 0.0), (4.0, 0.0)]
    mot_diem_dau = hai_opt(nearest_neighbour(list(danh_sach), _euclid), _euclid)
    ket_qua = sap_thu_tu(danh_sach, _euclid)
    assert set(ket_qua) == set(danh_sach)
    assert do_dai(ket_qua, _euclid) < do_dai(mot_diem_dau, _euclid)


def test_van_khong_dai_hon_thu_tu_ban_dau() -> None:
    """Hợp đồng cũ vẫn đứng sau khi thử nhiều điểm xuất phát: không dài hơn đầu vào."""
    ket_qua = sap_thu_tu(DIEM_COT_DINH, _euclid)
    assert do_dai(ket_qua, _euclid) <= do_dai(DIEM_COT_DINH, _euclid)


def test_van_xac_dinh_khi_thu_nhieu_diem_dau() -> None:
    """Cùng đầu vào (có điểm trùng nhau) chạy 20 lần ra đúng một kết quả."""
    danh_sach = [(0.0, 0.0), (1.0, 0.0), (0.0, 0.0), (1.0, 0.0), (0.5, 0.5)]
    lan_dau = sap_thu_tu(danh_sach, _euclid)
    for _ in range(19):
        assert sap_thu_tu(danh_sach, _euclid) == lan_dau


def test_chan_so_diem_dau() -> None:
    """12 điểm nhưng chỉ thử tối đa ``SO_DIEM_DAU_TOI_DA`` điểm xuất phát.

    Bọc ``nearest_neighbour`` bằng bộ đếm: không khóa vào một con số chính xác,
    chỉ khẳng định trần đã được áp dụng và không thử cả 12 điểm.
    """
    nguyen_goc = module.nearest_neighbour
    so_lan = [0]

    def _dem(diem, khoang_cach):
        so_lan[0] += 1
        return nguyen_goc(diem, khoang_cach)

    module.nearest_neighbour = _dem
    try:
        danh_sach = [(float(x), 0.0) for x in range(12)]
        sap_thu_tu(danh_sach, _euclid)
    finally:
        module.nearest_neighbour = nguyen_goc

    assert 1 <= so_lan[0] <= module.SO_DIEM_DAU_TOI_DA
    assert so_lan[0] < len(danh_sach)


def test_sap_thu_tu_dung_duoc_ham_do_bat_ky() -> None:
    """Đổi hàm đo thì đổi được thứ tự ghé — module không dính haversine.

    Bộ điểm tìm bằng quét thật: với các điểm này Euclid và Manhattan cho hai thứ
    tự khác nhau. Đây là bằng chứng ``sap_thu_tu`` chỉ phụ thuộc hàm đo, nên gói
    G3 có thể đút hàm đo đường đi thật vào mà không đổi dòng nào ở module này.
    """
    diem = [(0.0, 0.0), (0.0, 1.0), (0.0, 3.0), (1.0, 2.0)]

    thu_tu_euclid = sap_thu_tu(list(diem), _euclid)
    thu_tu_manhattan = sap_thu_tu(list(diem), _manhattan)

    assert set(thu_tu_euclid) == set(diem)
    assert set(thu_tu_manhattan) == set(diem)
    assert thu_tu_euclid != thu_tu_manhattan, (
        "Hai hàm đo khác nhau phải cho hai thứ tự khác nhau — nếu không gói G3 chưa cắm vào đúng chỗ"
    )
