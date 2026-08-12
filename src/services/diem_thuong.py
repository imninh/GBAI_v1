"""Cơ chế điểm thưởng — bộ máy tính điểm và sổ cái.

Ba lời hứa đứng sau module này (README, chú thích ở ``pickup_flow.py``, dải xanh
trên màn ban quản lý) giờ có mã đứng sau: **điểm chỉ được tính trên số cân do
người xác nhận**, không bao giờ trên ước lượng của AI.

Hai phần tách bạch:

* ``tinh_diem`` — hàm THUẦN: nhận số liệu, trả số liệu, không chạm CSDL. Test
  được bằng số trần.
* ``trao_diem`` — chạm CSDL: ghi một dòng sổ cái (``diem_thuong_log``) và cộng
  vào ``users.green_points``. Không ``commit`` — người gọi đang giữ một giao dịch.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import DiemThuongLog, PickupRequest, User
from src.services.auth import write_audit
from src.services.pickup_lifecycle import HOAN_TAT, chuan_hoa

# Điểm cho mỗi kg NGƯỜI CÂN được. Đây là phần duy nhất phụ thuộc khối lượng, và
# nó chỉ bao giờ được tính trên con số do người xác nhận.
DIEM_MOI_KG = 10

# Điểm thưởng cho mỗi MÓN, theo thang vật liệu.
#
# Vì sao tính theo SỐ MÓN chứ không theo kg từng loại: khối lượng trong CSDL gắn
# với cả yêu cầu (`weight_min_kg`/`weight_max_kg`), KHÔNG gắn với từng món — chia
# kg ra theo vật liệu là bịa một con số dữ liệu không đỡ nổi. Quyết định này đã
# chốt ở gói E4a và giữ nguyên ở đây.
#
# Thứ tự thang phản ánh "phân loại sai thì hại tới đâu, xử lý đúng thì tốn tới
# đâu", không phản ánh giá bán ve chai.
#
# ⚠️ Danh mục trong CSDL KHÔNG có nhóm "điện tử" riêng — `scripts/seed.py` chỉ có
# 9 mã, và đồ điện tử được phân vào `hazardous`. Nhu cầu "rác điện tử nhiều điểm"
# được đáp ứng qua thang `hazardous`; ĐỪNG bịa thêm mã nhóm mới trong gói này —
# thêm nhóm là đổi danh mục, đổi CLIP prompt, đổi eval — một gói riêng.
DIEM_MOI_MON = {
    "hazardous": 100,          # pin, bóng đèn, hoá chất — và ĐỒ ĐIỆN TỬ (xem chú thích dưới)
    "recyclable_metal": 40,
    "bulky": 30,
    "recyclable_glass": 25,
    "recyclable_paper": 15,
    "recyclable_plastic": 10,
    "organic": 5,
    "other": 2,
}


def tinh_diem(weight_confirmed_kg: float, items: list[dict]) -> dict:
    """Tính điểm cho một yêu cầu ĐÃ hoàn tất.

    Args:
        weight_confirmed_kg: khối lượng **người cân**, không phải ước lượng của AI.
        items: danh sách món ``[{name, category_code, qty}, …]`` của yêu cầu.

    Returns:
        ``{"diem", "diem_khoi_luong", "diem_vat_lieu", "chi_tiet"}``.
        ``chi_tiet`` bóc theo mã nhóm: ``{ma: {"so_mon": n, "diem": d}}``.
    """
    # Số cân âm hay 0 → không có phần khối lượng. Không nổ, trả 0.
    if weight_confirmed_kg and weight_confirmed_kg > 0:
        diem_khoi_luong = int(round(weight_confirmed_kg * DIEM_MOI_KG))
    else:
        diem_khoi_luong = 0

    chi_tiet: dict[str, dict[str, int]] = {}
    for mon in items or []:
        ma = str(mon.get("category_code") or "")
        if not ma:
            continue
        try:
            so_mon = int(mon.get("qty") or 1)
        except (TypeError, ValueError):
            so_mon = 1
        if so_mon < 1:
            so_mon = 1
        o = chi_tiet.setdefault(ma, {"so_mon": 0, "diem": 0})
        o["so_mon"] += so_mon
        o["diem"] += DIEM_MOI_MON.get(ma, 0) * so_mon

    diem_vat_lieu = sum(o["diem"] for o in chi_tiet.values())
    diem = diem_khoi_luong + diem_vat_lieu
    return {
        "diem": diem,
        "diem_khoi_luong": diem_khoi_luong,
        "diem_vat_lieu": diem_vat_lieu,
        "chi_tiet": chi_tiet,
    }


def trao_diem(session: Session, request: PickupRequest) -> DiemThuongLog | None:
    """Trao điểm cho một yêu cầu vừa hoàn tất. Trả ``None`` nếu không trao.

    Không trao khi: yêu cầu chưa ``hoan_tat`` · chưa có ``weight_confirmed_kg`` ·
    **đã có dòng sổ cái cho ``request_id`` này** (chống trao hai lần).

    Chống trao hai lần bằng truy vấn ``request_id`` TRƯỚC khi ghi — chạy được trên
    cả SQLite lẫn PostgreSQL, không dùng ``ON CONFLICT``. Không ``commit``.
    """
    if request.id is None:
        return None
    if chuan_hoa(request.status) != HOAN_TAT:
        return None
    if request.weight_confirmed_kg is None:
        return None

    da_co = session.scalar(select(DiemThuongLog.id).where(DiemThuongLog.request_id == request.id))
    if da_co is not None:
        return None

    ket_qua = tinh_diem(request.weight_confirmed_kg, request.items or [])

    dong = DiemThuongLog(
        user_id=request.resident_id,
        request_id=request.id,
        diem=ket_qua["diem"],
        diem_khoi_luong=ket_qua["diem_khoi_luong"],
        diem_vat_lieu=ket_qua["diem_vat_lieu"],
        weight_confirmed_kg=request.weight_confirmed_kg,
        chi_tiet=ket_qua["chi_tiet"],
        ly_do=f"Hoàn tất yêu cầu #PR-{request.id:04d}",
    )
    session.add(dong)

    nguoi_nhan = session.get(User, request.resident_id)
    if nguoi_nhan is not None:
        nguoi_nhan.green_points += ket_qua["diem"]

    # Trao điểm là thay đổi tài sản của người dùng — phải có vết. Actor là người
    # đã cân (xác nhận khối lượng) nếu có, để log nói được "ai châm ngòi".
    nguoi_xac_nhan = session.get(User, request.confirmed_by) if request.confirmed_by else None
    write_audit(
        session,
        actor=nguoi_xac_nhan,
        action="trao_diem",
        entity="pickup_request",
        entity_id=str(request.id),
        detail={
            "diem": ket_qua["diem"],
            "user_id": request.resident_id,
            "weight_confirmed_kg": request.weight_confirmed_kg,
        },
    )
    session.flush()
    return dong
