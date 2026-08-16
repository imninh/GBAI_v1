"""Test máy trạng thái yêu cầu thu gom — gói thuần, không cần session hay mạng."""

from __future__ import annotations

import pytest

from src.services.pickup_lifecycle import (
    CHUYEN_TIEP,
    HOAN_TAT,
    NHAN_VI,
    TRANG_THAI_KET_THUC,
    TU_CHOI,
    TU_TRANG_THAI_CU,
    LoiChuyenTrangThai,
    chuan_hoa,
    chuyen_trang_thai,
    co_the_chuyen,
    trang_thai_tuong_duong,
)

# --- Chuyển tiếp hợp lệ ------------------------------------------------------


def test_moi_buoc_chuyen_hop_le_trong_bang_deu_duoc_cho() -> None:
    for tu, cac_den in CHUYEN_TIEP.items():
        for den in cac_den:
            assert co_the_chuyen(tu, den), f"{tu} -> {den} phải được phép"
            assert chuyen_trang_thai(tu, den) == den


def test_khong_co_transition_khong_hop_le_trong_bang_duoc_cho() -> None:
    # Mọi bước trong bảng phải nằm đúng trong trạng thái gốc của chính nó.
    for tu, cac_den in CHUYEN_TIEP.items():
        for den in cac_den:
            assert den in CHUYEN_TIEP, f"{den} phải là một trạng thái đã khai báo"


# --- Chuyển tiếp bị cấm ------------------------------------------------------


@pytest.mark.parametrize(
    ("tu", "den"),
    [
        ("moi_tao", HOAN_TAT),  # đường tắt qua mặt người xác nhận khối lượng thật
        ("moi_tao", "da_nhan"),
        ("cho_duyet", HOAN_TAT),
        ("cho_duyet", "da_huy"),
        ("cho_nhan", HOAN_TAT),
        ("da_nhan", HOAN_TAT),
        ("dang_van_chuyen", HOAN_TAT),
        ("dang_van_chuyen", "da_huy"),
        ("da_giao_don_vi", "da_huy"),
        ("tranh_chap", "tu_choi"),
    ],
)
def test_buoc_chuyen_bat_hop_le_nem_loi(tu: str, den: str) -> None:
    assert not co_the_chuyen(tu, den)
    with pytest.raises(LoiChuyenTrangThai):
        chuyen_trang_thai(tu, den)


def test_ba_trang_thai_ket_thuc_khong_cho_chuyen_ra() -> None:
    assert TRANG_THAI_KET_THUC == {"hoan_tat", "tu_choi", "da_huy"}
    for tu in TRANG_THAI_KET_THUC:
        assert CHUYEN_TIEP[tu] == frozenset(), f"{tu} là trạng thái kết thúc"
        for den in CHUYEN_TIEP:
            with pytest.raises(LoiChuyenTrangThai):
                chuyen_trang_thai(tu, den)


# --- Trạng thái không tồn tại ------------------------------------------------


@pytest.mark.parametrize("tu", ["khong_co", "DANG_VAN_CHUYEN", "đã xong"])
def test_trang_thai_nguon_khong_biet_nem_loi(tu: str) -> None:
    assert not co_the_chuyen(tu, "moi_tao")
    with pytest.raises(LoiChuyenTrangThai):
        chuyen_trang_thai(tu, "moi_tao")


@pytest.mark.parametrize("den", ["khong_co", "HOAN_TAT", "xong rồi"])
def test_trang_thai_dich_khong_biet_nem_loi(den: str) -> None:
    assert not co_the_chuyen("moi_tao", den)
    with pytest.raises(LoiChuyenTrangThai):
        chuyen_trang_thai("moi_tao", den)


# --- Nhãn hiển thị ------------------------------------------------------------


def test_moi_trang_thai_trong_chuyen_tiep_deu_co_nhan_va_nguoc_lai() -> None:
    assert set(CHUYEN_TIEP) == set(NHAN_VI), "Bảng chuyển tiếp và nhãn phải khớp nhau"
    assert all(label for label in NHAN_VI.values()), "Không được có nhãn rỗng"
    assert len(NHAN_VI) == 10


# --- Hàm chuyển trả về đúng giá trị ------------------------------------------


def test_chuyen_trang_thai_tra_ve_den_khi_hop_le() -> None:
    assert chuyen_trang_thai("moi_tao", "cho_duyet") == "cho_duyet"
    assert chuyen_trang_thai("cho_duyet", "cho_nhan") == "cho_nhan"
    assert chuyen_trang_thai("da_giao_don_vi", HOAN_TAT) == HOAN_TAT


def test_loi_chuyen_trang_thai_mang_dien_tin_hai_trang_thai() -> None:
    with pytest.raises(LoiChuyenTrangThai) as thong_tin:
        chuyen_trang_thai("moi_tao", HOAN_TAT)
    loi = str(thong_tin.value)
    assert "moi_tao" in loi
    assert HOAN_TAT in loi


# --- Ánh xạ trạng thái cũ -> mới ----------------------------------------------


@pytest.mark.parametrize(
    ("cu", "moi"),
    [
        ("pending", "cho_duyet"),
        ("approved", "cho_nhan"),
        ("scheduled", "da_nhan"),
        ("done", "hoan_tat"),
        ("cancelled", "da_huy"),
    ],
)
def test_moi_gia_tri_cu_map_dung_gia_tri_moi(cu: str, moi: str) -> None:
    assert chuan_hoa(cu) == moi


def test_moi_gia_tri_map_trong_bang_la_trang_thai_toi_ton_tai() -> None:
    for cu, moi in {
        "pending": "cho_duyet",
        "approved": "cho_nhan",
        "scheduled": "da_nhan",
        "done": "hoan_tat",
        "cancelled": "da_huy",
    }.items():
        assert moi in CHUYEN_TIEP, f"{cu} phải trỏ tới một trạng thái có thật"


def test_gia_tri_moi_qua_chuan_hoa_duoc_giu_nguyen() -> None:
    for trang_thai in CHUYEN_TIEP:
        assert chuan_hoa(trang_thai) == trang_thai


def test_chuoi_rong_ve_moi_tao() -> None:
    assert chuan_hoa("") == "moi_tao"


def test_chuoi_khong_biet_nem_loi() -> None:
    with pytest.raises(LoiChuyenTrangThai):
        chuan_hoa("khong_co_trang_thai_nay")
    with pytest.raises(LoiChuyenTrangThai):
        chuan_hoa("DA_HUY")


def test_tu_vung_cu_va_moi_khong_trung_nhau() -> None:
    cu = {"pending", "approved", "scheduled", "done", "cancelled"}
    moi = set(CHUYEN_TIEP)
    assert cu.isdisjoint(moi), "Trạng thái cũ không được trùng tên trạng thái mới"


# --- Từ vựng tương đương cho truy vấn SQL --------------------------------------


def test_trang_thai_tuong_duong_moi_dung_truoc_cu() -> None:
    assert trang_thai_tuong_duong(HOAN_TAT) == (HOAN_TAT, "done")
    assert trang_thai_tuong_duong("cho_nhan") == ("cho_nhan", "approved")
    assert trang_thai_tuong_duong("da_nhan") == ("da_nhan", "scheduled")
    assert trang_thai_tuong_duong("cho_duyet") == ("cho_duyet", "pending")
    assert trang_thai_tuong_duong("da_huy") == ("da_huy", "cancelled")


def test_moi_trang_thai_deu_duoc_chap_nhan_va_chua_chinh_no() -> None:
    for trang_thai in CHUYEN_TIEP:
        bo_tuong_duong = trang_thai_tuong_duong(trang_thai)
        assert trang_thai in bo_tuong_duong
        assert bo_tuong_duong[0] == trang_thai


def test_trang_thai_ket_thuc_khong_co_cu_tuong_duong_tra_tuple_mot_phan_tu() -> None:
    # "moi_tao" không có giá trị cũ → tuple một phần tử. Các trạng thái kết thúc
    # khác đều có: "tu_choi" ↔ "rejected", "hoan_tat" ↔ "done", "da_huy" ↔ "cancelled".
    assert trang_thai_tuong_duong("moi_tao") == ("moi_tao",)
    assert trang_thai_tuong_duong("tu_choi") == ("tu_choi", "rejected")


def test_trang_thai_khong_biet_nem_loi_trong_tuong_duong() -> None:
    with pytest.raises(LoiChuyenTrangThai):
        trang_thai_tuong_duong("khong_co_trang_thai_nay")
    with pytest.raises(LoiChuyenTrangThai):
        trang_thai_tuong_duong("pending")


def test_hop_cua_moi_trang_thai_moi_phu_dung_mot_lan_toan_bo_tu_vung_cu() -> None:
    """Mỗi giá trị cũ phải tới được từ ĐÚNG MỘT trạng thái mới — không được có
    hai trạng thái mới cùng nhận một giá trị cũ."""
    cac_gia_tri_cu: list[str] = []
    for trang_thai in CHUYEN_TIEP:
        cac_gia_tri_cu.extend(trang_thai_tuong_duong(trang_thai)[1:])

    assert sorted(cac_gia_tri_cu) == sorted({"pending", "approved", "scheduled", "done", "cancelled", "rejected"})


# --- Giá trị cũ "rejected" -----------------------------------------------


def test_chuan_hoa_rejected_ve_tu_choi() -> None:
    assert chuan_hoa("rejected") == TU_CHOI


def test_trang_thai_tuong_duong_tu_choi_chua_ca_rejected() -> None:
    assert trang_thai_tuong_duong(TU_CHOI) == (TU_CHOI, "rejected")


def test_sau_gia_tri_cu_dung_la_toan_bo_khoa_cua_bang() -> None:
    """Chốt danh sách theo văn tự — thêm giá trị thứ bảy sau này sẽ vỡ ngay tại đây."""
    assert set(TU_TRANG_THAI_CU) == {"pending", "approved", "scheduled", "done", "cancelled", "rejected"}


def test_tu_vung_cu_va_moi_van_tach_biet_sau_khi_them_rejected() -> None:
    cu = set(TU_TRANG_THAI_CU)
    moi = set(CHUYEN_TIEP)
    assert cu.isdisjoint(moi), "Trạng thái cũ không được trùng tên trạng thái mới"
