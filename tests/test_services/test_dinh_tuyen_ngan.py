"""Test ánh xạ nhóm rác → ngăn vật lý trên thiết bị phân loại (CP2).

Bảng ánh xạ này đã được đối chiếu với CSDL production (9/9 mã nhóm rác thật)
và KHÔNG được "cải tiến" thành đoán theo tên chuỗi — test dưới đây khoá chặt
hành vi hiện có để ai đó không lỡ tay đổi.
"""

from __future__ import annotations

import pytest

from src.services.dinh_tuyen_ngan import (
    BANG_ANH_XA,
    NGAN_METAL,
    NGAN_OTHER,
    NGAN_PAPER,
    NGAN_PLASTIC,
    nhom_rac_den_ngan,
)

BON_NGAN = {NGAN_PLASTIC, NGAN_METAL, NGAN_PAPER, NGAN_OTHER}


def test_ba_nhom_co_ngan_rieng() -> None:
    assert nhom_rac_den_ngan("recyclable_plastic") == NGAN_PLASTIC
    assert nhom_rac_den_ngan("recyclable_metal") == NGAN_METAL
    assert nhom_rac_den_ngan("recyclable_paper") == NGAN_PAPER


@pytest.mark.parametrize(
    "ma_nhom",
    ["hazardous", "organic", "bulky", "other", "recyclable_glass", "recyclable"],
)
def test_nhom_con_lai_deu_ve_ngan_an_toan(ma_nhom: str) -> None:
    """Nguy hại, rác ướt, cồng kềnh, mã cha, thuỷ tinh → ngăn an toàn."""
    assert nhom_rac_den_ngan(ma_nhom) == NGAN_OTHER


@pytest.mark.parametrize("ma_nhom", [None, ""])
def test_none_va_chuoi_rong_deu_ve_ngan_an_toan(ma_nhom: str | None) -> None:
    assert nhom_rac_den_ngan(ma_nhom) == NGAN_OTHER


def test_ma_bia_chua_tung_ton_tai_ve_ngan_an_toan() -> None:
    assert nhom_rac_den_ngan("ma_bia_chua_tung_ton_tai") == NGAN_OTHER


@pytest.mark.parametrize("ma_nhom", list(BANG_ANH_XA))
def test_quet_toan_bo_bang_anh_xa_khong_ra_ngan_thu_nam(ma_nhom: str) -> None:
    """Quét toàn bộ bảng: mọi mã phải về một trong đúng bốn ngăn firmware biết.

    Ngăn thứ năm xuất hiện là firmware ESP32 không hiểu — firmware chỉ thực thi
    ``route`` (ADR-0012), nên tuyệt đối không được thêm ngăn lạ.
    """
    assert nhom_rac_den_ngan(ma_nhom) in BON_NGAN
