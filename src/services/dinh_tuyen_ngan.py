"""Ánh xạ nhóm rác → ngăn vật lý trên thiết bị phân loại (CP2).

Thiết bị ESP32-CAM có 4 ngăn: ``plastic`` · ``metal`` · ``paper`` · ``other``.
Bảng ánh xạ khai TƯỜNG MINH theo mã nhóm rác của hệ thống — không đoán theo tên
chuỗi. Mã nào không có trong bảng (nhóm mới, nhóm nguy hại…) → ``other``, là ngăn
an toàn để dây chuyền không đứng.

Yêu cầu kiến trúc (ADR-0012): firmware chỉ THỰC THI ``route``, không tự đặt ngưỡng
và không tự quyết nhãn. Phần quyết nhãn thuộc về pipeline phân loại hiện có; chỗ
này chỉ trả lời "nhóm rác này đổ vào ngăn nào".
"""

from __future__ import annotations

from typing import Final

# Bốn ngăn vật lý cố định của thiết bị.
NGAN_PLASTIC: Final[str] = "plastic"
NGAN_METAL: Final[str] = "metal"
NGAN_PAPER: Final[str] = "paper"
NGAN_OTHER: Final[str] = "other"

# Mã nhóm rác hệ thống (seed_data.py) → ngăn vật lý. Khai tường minh từng mã.
BANG_ANH_XA: Final[dict[str, str]] = {
    "recyclable_plastic": NGAN_PLASTIC,
    "recyclable_metal": NGAN_METAL,
    "recyclable_paper": NGAN_PAPER,
    # "recyclable" là nhóm tổng (cha) — thiết bị không biết đổ ngăn nào nếu chỉ
    # có mã cha, nên ưu tiên ngăn an toàn. Các nhóm con đã khai ở trên.
    "recyclable": NGAN_OTHER,
    "recyclable_glass": NGAN_OTHER,  # chưa có ngăn thuỷ tinh trên thiết bị
    # Nhóm còn lại (organic, other, hazardous, bulky) đều về ngăn an toàn.
}


def nhom_rac_den_ngan(ma_nhom: str | None) -> str:
    """Trả về ngăn vật lý cho một mã nhóm rác.

    Args:
        ma_nhom: mã nhóm rác của hệ thống (``predicted_category.code``).

    Returns:
        Tên ngăn: ``plastic`` | ``metal`` | ``paper`` | ``other``. Mã rỗng,
        mã không có trong bảng, hay nhóm nguy hại đều → ``other`` (an toàn).
    """
    if not ma_nhom:
        return NGAN_OTHER
    return BANG_ANH_XA.get(ma_nhom, NGAN_OTHER)
