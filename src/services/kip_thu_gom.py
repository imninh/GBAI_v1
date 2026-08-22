"""Quản lý kíp thu gom — một chuyến hai người, gán theo vòng tròn.

Gói P80 — ba mảng:

1. **Phân công theo vòng tròn.** Danh sách nhân viên thu gom đang hoạt động
   (``role == "cleaner"``), sắp xếp tất định theo ``id``. Ai ít chuyến nhất
   trong tuần thì được xếp trước; hoà thì ``id`` nhỏ hơn. Hoàn toàn tất định,
   không ``random``.

2. **Gán / thay đổi kíp.** ``gan_kip`` là phần "có thể chỉnh sửa" mà người
   duyệt yêu cầu. Gán lại xoá thành viên cũ rồi ghi mới trong cùng một giao
   dịch.

3. **Đồng bộ ``team_id``.** ``PickupRoute.team_id`` giữ nguyên (trưởng kíp),
   không xoá — screen đang chạy và test cũ dùng nó. Hàm ``gan_kip`` đồng bộ
   ``team_id = truong_kip_id`` trong mọi lần gán.
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.db.models import PickupRoute, RouteThanhVien, User
from src.services.auth import write_audit

_LOG = logging.getLogger(__name__)

# Một xe hai người — giả định của người duyệt ngày 21/08, chưa có dữ liệu
# doanh nghiệp thật.
SO_NGUOI_MOI_KIP = 2


# ---------------------------------------------------------------------------
# Danh sách nhân viên
# ---------------------------------------------------------------------------


def nhan_vien_kha_dung(session: Session) -> list[User]:
    """Nhân viên thu gom đang hoạt động.

    Hiện tại hệ thống chưa có ``User.is_active`` — mọi ``cleaner`` đều tính
    là đang hoạt động. Sắp xếp tất định theo ``id``.
    """
    return list(session.scalars(select(User).where(User.role == "cleaner").order_by(User.id)).all())


# ---------------------------------------------------------------------------
# Gán / thay đổi kíp
# ---------------------------------------------------------------------------


def gan_kip(
    session: Session,
    *,
    actor: User,
    route_id: int,
    user_ids: list[int],
    truong_kip_id: int | None = None,
) -> dict:
    """Gán hoặc gán lại kíp cho một chuyến.

    ``user_ids`` phải đúng ``SO_NGUOI_MOI_KIP`` người, mọi người đều là
    ``cleaner`` đang hoạt động, không trùng. ``truong_kip_id`` mặc định là
    người đầu tiên trong danh sách.

    Chuyến ``done`` hoặc đã xác nhận (``xac_nhan_boi`` khác ``None``) → từ
    chối đổi kíp.

    ``team_id`` trên ``PickupRoute`` luôn được đồng bộ thành ``truong_kip_id``
    (§3.1).
    """
    route = session.get(PickupRoute, route_id)
    if route is None:
        raise ValueError("Không tìm thấy tuyến này")

    if route.status == "done" or route.xac_nhan_boi is not None:
        raise ValueError("Chuyến đã hoàn tất hoặc đã được xác nhận — không đổi kíp được")

    if len(user_ids) != SO_NGUOI_MOI_KIP:
        raise ValueError(f"Một kíp phải đúng {SO_NGUOI_MOI_KIP} người — bạn gửi {len(user_ids)}.")

    if len(set(user_ids)) != len(user_ids):
        raise ValueError("Không được gán cùng một người hai lần trong một kíp")

    hop_le_ids = {u.id for u in nhan_vien_kha_dung(session)}
    for uid in user_ids:
        if uid not in hop_le_ids:
            raise ValueError("Một người được gán không phải nhân viên thu gom đang hoạt động")

    if truong_kip_id is None:
        truong_kip_id = user_ids[0]
    if truong_kip_id not in user_ids:
        raise ValueError("Trưởng kíp phải nằm trong danh sách thành viên")

    cu = kip_cua_chuyen(session, route_id=route_id)
    cu_ids = [m["id"] for m in cu]

    session.execute(delete(RouteThanhVien).where(RouteThanhVien.route_id == route_id))
    for uid in user_ids:
        vai = "truong_kip" if uid == truong_kip_id else "thanh_vien"
        session.add(RouteThanhVien(route_id=route_id, user_id=uid, vai_tro=vai))

    route.team_id = truong_kip_id

    write_audit(
        session,
        actor=actor,
        action="route_gan_kip",
        entity="pickup_route",
        entity_id=str(route_id),
        detail={"tu": cu_ids, "den": user_ids, "truong_kip": truong_kip_id},
    )
    session.flush()

    return {"route_id": route_id, "user_ids": user_ids, "truong_kip_id": truong_kip_id}


# ---------------------------------------------------------------------------
# Đọc kíp
# ---------------------------------------------------------------------------


def kip_cua_chuyen(session: Session, *, route_id: int) -> list[dict]:
    """Thành viên kíp của chuyến. Trả ``[{id, full_name, vai_tro}]``.

    ⚠️ Không trả số điện thoại, không trả email.
    """
    rows = session.execute(
        select(RouteThanhVien, User)
        .join(User, User.id == RouteThanhVien.user_id)
        .where(RouteThanhVien.route_id == route_id)
        .order_by(RouteThanhVien.id)
    ).all()

    thanh_vien = [{"id": u.id, "full_name": u.full_name, "vai_tro": rtv.vai_tro} for rtv, u in rows]
    thanh_vien.sort(key=lambda m: (m["vai_tro"] != "truong_kip", m["id"]))
    return thanh_vien


# ---------------------------------------------------------------------------
# Chọn kíp tự động (vòng tròn — §3.2)
# ---------------------------------------------------------------------------


def chon_kip_tu_dong(
    session: Session,
    *,
    tuan_bat_dau: date,
    da_gan: dict[int, int],
) -> list[int] | None:
    """Chọn ``SO_NGUOI_MOI_KIP`` người ít chuyến nhất, cập nhật ``da_gan``.

    * ``da_gan`` — bảng đếm số chuyến đã xếp cho từng người **trong lượt
      chạy này**, để lượt sau không dồn hết vào một người. Bảng này được
      ``tao_lich_tuan`` tạo mới mỗi lần gọi, mỗi lần ``chon_kip_tu_dong``
      tự ``+= 1`` cho người được chọn.
    * Nếu số nhân viên **ít hơn** ``SO_NGUOI_MOI_KIP`` → trả ``None``, không
      tạo kíp thiếu người.
    * Hoàn toàn **tất định**: cùng đầu vào ra cùng kết quả.
    """
    nhan_vien = nhan_vien_kha_dung(session)
    if len(nhan_vien) < SO_NGUOI_MOI_KIP:
        return None

    chon = sorted(nhan_vien, key=lambda u: (da_gan.get(u.id, 0), u.id))[: SO_NGUOI_MOI_KIP]
    for u in chon:
        da_gan[u.id] = da_gan.get(u.id, 0) + 1
    return [u.id for u in chon]
