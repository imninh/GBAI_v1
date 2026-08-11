"""Bảng ánh xạ RealWaste phải trỏ vào mã nhóm rác có thật trong CSDL."""

from __future__ import annotations

from pathlib import Path

from eval.chuan_bi_realwaste import ANH_XA_LOP, _lay_mau_deu
from src.db.seed_data import WASTE_CATEGORIES


def test_moi_ma_nhom_deu_co_that_trong_danh_muc() -> None:
    """Ánh xạ sai mã nhóm thì run_eval.py sẽ lặng lẽ bỏ qua cả thư mục."""
    ma_hop_le = {c["code"] for c in WASTE_CATEGORIES}
    for ten_lop, ma_nhom in ANH_XA_LOP.items():
        assert ma_nhom in ma_hop_le, f"'{ten_lop}' trỏ vào mã không tồn tại: {ma_nhom}"


def test_du_chin_lop_cua_realwaste() -> None:
    assert len(ANH_XA_LOP) == 9


def test_khong_anh_xa_vao_nhom_nguy_hai() -> None:
    """RealWaste không có ảnh rác nguy hại — gán nhầm vào đó là tự bịa nhãn."""
    assert "hazardous" not in set(ANH_XA_LOP.values())


def test_lay_mau_deu_tra_ve_dung_so_luong_va_tat_dinh() -> None:
    tep = [Path(f"{i:03d}.jpg") for i in range(100)]
    mau = _lay_mau_deu(tep, 10)
    assert len(mau) == 10
    assert mau == _lay_mau_deu(tep, 10)
    # Rải đều nghĩa là KHÔNG phải 10 ảnh đầu.
    assert mau != tep[:10]


def test_it_hon_so_can_lay_thi_tra_ve_het() -> None:
    tep = [Path(f"{i}.jpg") for i in range(5)]
    assert _lay_mau_deu(tep, 20) == tep
