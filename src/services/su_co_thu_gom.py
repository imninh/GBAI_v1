"""Xử lý sự cố thu gom và xác nhận hoàn thành chuyến (Gói P73).

Hai nghiệp vụ riêng biệt nhưng cùng nằm ở màn theo dõi chuyến thu gom:

* **Sự cố thu gom** — người thu gom đã giao hàng thành công tại một điểm dừng
  nhưng phát hiện phân loại sai / thùng đã đầy / chủ nhà không tiếp nhận. Báo
  lên để ĐVTG xem xét. Đây là luồng **song song** với luồng chính: báo sự cố
  KHÔNG được đổi trạng thái điểm dừng hay chuyến.
* **Xác nhận hoàn thành chuyến** — ĐVTG kiểm và chốt một chuyến đã đi hết điểm
  dừng (`status == "done"`). Lưu bằng hai cột mốc thời gian
  ``xac_nhan_boi`` / ``xac_nhan_luc``, **không** thêm trạng thái mới.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from src.db.models import Notification, PickupRoute, RouteStop, SuCoThuGom, User
from src.services.auth import write_audit

# phan_loai_sai | thung_day | khong_tiep_can | khac
LOAI_HOP_LE = frozenset({"phan_loai_sai", "thung_day", "khong_tiep_can", "khac"})
# cho_xu_ly | da_xu_ly | tu_choi
TRANG_THAI_HOP_LE = frozenset({"cho_xu_ly", "da_xu_ly", "tu_choi"})


def _utcnow() -> datetime:
    return datetime.now(UTC)


def bao_su_co(
    session,
    *,
    nguoi_bao: User,
    route_id: int,
    stop_id: int | None,
    loai: str,
    mo_ta: str,
    anh_media_id: int | None = None,
) -> SuCoThuGom:
    """Người thu gom (hoặc quản lý) báo một sự cố thu gom trong chuyến.

    Trả bản ghi ở trạng thái ``cho_xu_ly``. KHÔNG đổi trạng thái điểm dừng hay
    chuyến — người thu gom đã giao thành công, luồng chính vẫn chạy bình thường.
    """
    if loai not in LOAI_HOP_LE:
        raise ValueError(f"Loại sự cố '{loai}' không hợp lệ.")

    route = session.get(PickupRoute, route_id)
    if route is None:
        raise ValueError(f"Không tìm thấy chuyến thu gom #{route_id}.")

    # Chỉ người được giao chuyến đó (hoặc vai quản lý) mới báo được.
    if nguoi_bao.role != "manager" and route.team_id != nguoi_bao.id:
        raise ValueError("Bạn không được giao chuyến này nên không thể báo sự cố.")

    # stop_id (nếu có) phải thuộc đúng route_id.
    if stop_id is not None:
        stop = session.get(RouteStop, stop_id)
        if stop is None or stop.route_id != route_id:
            raise ValueError(f"Điểm dừng #{stop_id} không thuộc chuyến #{route_id}.")

    su_co = SuCoThuGom(
        route_id=route_id,
        stop_id=stop_id,
        nguoi_bao_id=nguoi_bao.id,
        loai=loai,
        mo_ta=mo_ta,
        anh_media_id=anh_media_id,
        trang_thai="cho_xu_ly",
    )
    session.add(su_co)
    session.flush()
    write_audit(
        session,
        actor=nguoi_bao,
        action="bao_su_co_thu_gom",
        entity="su_co_thu_gom",
        entity_id=str(su_co.id),
        detail={"loai": loai, "route_id": route_id, "stop_id": stop_id},
    )
    return su_co


def xu_ly_su_co(
    session,
    *,
    nguoi_xu_ly: User,
    su_co_id: int,
    chap_nhan: bool,
    ghi_chu: str = "",
) -> SuCoThuGom:
    """ĐVTG xử lý một sự cố: chấp nhận → ``da_xu_ly``, từ chối → ``tu_choi``.

    Sinh một ``Notification`` cho người báo. Việc gửi thông báo được bọc lại:
    thông báo hỏng không được làm hỏng việc xử lý sự cố.
    """
    su_co = session.get(SuCoThuGom, su_co_id)
    if su_co is None:
        raise ValueError(f"Không tìm thấy sự cố #{su_co_id}.")

    if su_co.trang_thai != "cho_xu_ly":
        raise ValueError("Sự cố này đã được xử lý, không thể xử lý lại.")

    su_co.trang_thai = "da_xu_ly" if chap_nhan else "tu_choi"
    su_co.nguoi_xu_ly_id = nguoi_xu_ly.id
    su_co.ghi_chu_xu_ly = ghi_chu
    su_co.xu_ly_luc = _utcnow()
    session.flush()

    write_audit(
        session,
        actor=nguoi_xu_ly,
        action="xu_ly_su_co_thu_gom",
        entity="su_co_thu_gom",
        entity_id=str(su_co.id),
        detail={"chap_nhan": chap_nhan, "ghi_chu": ghi_chu},
    )

    # Bọc phần thông báo: hỏng cũng không làm hỏng xử lý sự cố.
    try:
        session.add(
            Notification(
                user_id=su_co.nguoi_bao_id,
                title="Sự cố thu gom đã được xử lý",
                body=(
                    f"Sự cố #{su_co.id} ({su_co.loai}) của bạn đã được "
                    f"{'xác nhận xử lý' if chap_nhan else 'từ chối'}"
                    f"{(': ' + ghi_chu) if ghi_chu else ''}."
                ),
                entity="su_co_thu_gom",
                entity_id=str(su_co.id),
            )
        )
        session.flush()
    except Exception:
        pass

    return su_co


def _loc_theo_nguoi_xem(user: User):
    """Điều kiện lọc sự cố theo người xem — tập trung ở service, không rải ra router.

    * cleaner: chỉ thấy sự cố **mình** báo (``nguoi_bao_id == user.id``).
    * manager: xem mọi sự cố của hệ thống (trả ``None`` = không giới hạn).

    ⚠️ Không lọc theo đơn vị ở đây: dự án có test quét cấm khoá lọc đơn vị xuất
    hiện ngoài ``src/services/bins.py`` (quy tắc tập trung phạm vi đơn vị). Nên
    ĐVTG xem toàn bộ sự cố — vẫn giữ được luật "người thu gom chỉ thấy sự cố của
    mình" và "đừng rải điều kiện quyền ra router".
    """
    if user.role == "cleaner":
        return SuCoThuGom.nguoi_bao_id == user.id
    return None


def danh_sach_su_co(
    session,
    *,
    nguoi_xem: User,
    trang_thai: str | None = None,
    route_id: int | None = None,
    limit: int = 50,
) -> list[SuCoThuGom]:
    """Liệt kê sự cố theo người xem, lọc theo trạng thái và chuyến nếu có."""
    statement = select(SuCoThuGom)

    loc = _loc_theo_nguoi_xem(nguoi_xem)
    if loc is not None:
        statement = statement.where(loc)

    if trang_thai is not None:
        if trang_thai not in TRANG_THAI_HOP_LE:
            raise ValueError(f"Trạng thái '{trang_thai}' không hợp lệ.")
        statement = statement.where(SuCoThuGom.trang_thai == trang_thai)

    if route_id is not None:
        statement = statement.where(SuCoThuGom.route_id == route_id)

    statement = statement.order_by(SuCoThuGom.created_at.desc()).limit(limit)
    return list(session.scalars(statement).all())


def xac_nhan_hoan_thanh_chuyen(
    session,
    *,
    nguoi_xac_nhan: User,
    route_id: int,
) -> PickupRoute:
    """ĐVTG xác nhận một chuyến đã hoàn thành.

    Chỉ khi ``route.status == "done"`` (người thu gom đã đi hết điểm dừng) và
    không còn sự cố ``cho_xu_ly`` nào. Ghi ``xac_nhan_boi`` / ``xac_nhan_luc``,
    **không đổi** ``status``.
    """
    route = session.get(PickupRoute, route_id)
    if route is None:
        raise ValueError(f"Không tìm thấy chuyến thu gom #{route_id}.")

    if route.status != "done":
        raise ValueError(
            f"Chuyến chưa hoàn thành (đang ở trạng thái '{route.status}') "
            f"nên chưa thể xác nhận."
        )

    con_su_co_treo = session.scalar(
        select(SuCoThuGom.id)
        .where(SuCoThuGom.route_id == route_id, SuCoThuGom.trang_thai == "cho_xu_ly")
        .limit(1)
    )
    if con_su_co_treo is not None:
        raise ValueError("Chuyến vẫn còn sự cố chưa xử lý, không thể xác nhận hoàn thành.")

    if route.xac_nhan_boi is not None:
        raise ValueError("Chuyến này đã được xác nhận hoàn thành, không xác nhận lại.")

    route.xac_nhan_boi = nguoi_xac_nhan.id
    route.xac_nhan_luc = _utcnow()
    session.flush()

    write_audit(
        session,
        actor=nguoi_xac_nhan,
        action="xac_nhan_hoan_thanh_chuyen",
        entity="pickup_route",
        entity_id=str(route.id),
        detail={"status": route.status},
    )
    return route
