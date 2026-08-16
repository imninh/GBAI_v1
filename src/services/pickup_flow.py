"""Đẩy một yêu cầu thu gom dọc theo máy trạng thái — luồng của đội vệ sinh.

Tách khỏi ``pickup.py`` vì module đó đã vượt 300 dòng. Chức năng ở đây là một
lối đi gọn: đọc trạng thái qua ``chuan_hoa`` (chịu cả hai từ vựng trong lúc di
trú), kiểm bước đi bằng ``chuyen_trang_thai`` rồi ghi một mốc ``PickupEvent``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from src.config import get_settings
from src.db.models import PickupEvent, PickupRequest, User
from src.services.diem_thuong import trao_diem
from src.services.pickup_lifecycle import (
    DA_GIAO_DON_VI,
    HOAN_TAT,
    TRANH_CHAP,
    LoiChuyenTrangThai,
    chuan_hoa,
    chuyen_trang_thai,
)


def chuyen_trang_thai_yeu_cau(
    session: Session,
    request: PickupRequest,
    den: str,
    actor: User,
    ghi_chu: str = "",
) -> PickupRequest:
    """Chuyển một yêu cầu sang trạng thái ``den`` và ghi mốc lên timeline.

    Raises:
        ValueError: bước chuyển không hợp lệ hoặc trạng thái đích không tồn tại
            — thông điệp nêu rõ cả trạng thái nguồn lẫn trạng thái đích.
    """
    tu = chuan_hoa(request.status)
    try:
        den_chuan = chuan_hoa(den)
        chuyen_trang_thai(tu, den_chuan)
    except LoiChuyenTrangThai as exc:
        raise ValueError(f"Không thể chuyển yêu cầu từ '{tu}' sang '{den}'.") from exc

    request.status = den_chuan
    session.add(
        PickupEvent(
            request_id=request.id,
            kind="status_changed",
            label_vi=f"Trạng thái chuyển từ '{tu}' sang '{den_chuan}'",
            actor_id=actor.id,
            detail={"ghi_chu": ghi_chu},
        )
    )
    session.flush()
    return request


def xac_nhan_khoi_luong(
    session: Session,
    request: PickupRequest,
    weight_confirmed_kg: float,
    actor: User,
) -> PickupRequest:
    """Chốt khối lượng THẬT do đội vệ sinh cân và đẩy yêu cầu về đích.

    Khối lượng thật được so với khoảng ``weight_min_kg..weight_max_kg`` (kèm
    dung sai ``PICKUP_WEIGHT_TOLERANCE_PERCENT``):
    trong khoảng → ``hoan_tat``; lệch quá → ``tranh_chap`` kèm lý do.

    Raises:
        ValueError: yêu cầu chưa tới ``da_giao_don_vi`` (chưa thể cân thật),
            hoặc cân nặng âm.
    """
    tu = chuan_hoa(request.status)
    if tu != DA_GIAO_DON_VI:
        raise ValueError(f"Chỉ xác nhận khối lượng khi đã giao đơn vị thu gom, hiện đang ở '{tu}'.")
    if weight_confirmed_kg < 0:
        raise ValueError("Khối lượng xác nhận không thể âm.")

    # ⚠️ Điểm THƯỞNG chỉ được trao từ khối lượng THẬT do con người cân và xác
    # nhận. Không bao giờ dùng ``est_weight_kg`` hay cận của AI để chốt — sai
    # một chút ở đây là trao điểm trên một con số ước lượng, phá mất toàn bộ
    # ý nghĩa của máy trạng thái này.
    settings = get_settings()
    dung_sai = settings.pickup_weight_tolerance_percent / 100.0
    duoi = request.weight_min_kg * (1 - dung_sai)
    tren = request.weight_max_kg * (1 + dung_sai)

    if duoi <= weight_confirmed_kg <= tren:
        den = HOAN_TAT
        request.dispute_reason = ""
    else:
        den = TRANH_CHAP
        request.dispute_reason = (
            f"Khối lượng thật {weight_confirmed_kg:g} kg lệch ngoài khoảng "
            f"ước lượng {request.weight_min_kg:g}–{request.weight_max_kg:g} kg"
        )

    try:
        chuyen_trang_thai(tu, den)
    except LoiChuyenTrangThai as exc:
        raise ValueError(f"Không thể chuyển yêu cầu từ '{tu}' sang '{den}'.") from exc

    request.status = den
    request.weight_confirmed_kg = weight_confirmed_kg
    request.confirmed_by = actor.id
    request.confirmed_at = datetime.now()
    session.add(
        PickupEvent(
            request_id=request.id,
            kind="confirmed",
            label_vi=(
                f"Đã cân khối lượng thật {weight_confirmed_kg:g} kg — hoàn tất"
                if den == HOAN_TAT
                else f"Đã cân khối lượng thật {weight_confirmed_kg:g} kg — rơi vào tranh chấp"
            ),
            actor_id=actor.id,
            detail={"weight_confirmed_kg": weight_confirmed_kg, "dispute_reason": request.dispute_reason},
        )
    )
    # Điểm chỉ trao khi kiện thật sự hoàn tất. Rơi vào tranh chấp thì KHÔNG trao
    # điểm nào — con số còn đang bị nghi ngờ thì chưa được biến thành tài sản.
    if den == HOAN_TAT:
        trao_diem(session, request)
    session.flush()
    return request
