"""Yêu cầu thu gom và hàng đợi duyệt — HITL #1."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from src.api.deps import CurrentUser, DbSession, require
from src.api.errors import bad_request, forbidden, not_found
from src.api.serializers import pickup_dict
from src.db.models import PickupRequest, SuCoThuGom, Unit, User
from src.db.seed_data import PICKUP_REJECT_REASONS
from src.models.schemas import CreatePickupRequest, ReviewPickupRequest
from src.services import pickup as pickup_service
from src.services import pickup_flow, su_co_thu_gom
from src.services.auth import can, write_audit
from src.services.pickup_lifecycle import (
    CHO_DUYET,
    CHO_NHAN,
    LoiChuyenTrangThai,
    chuan_hoa,
    trang_thai_tuong_duong,
)

router = APIRouter(prefix="/pickups", tags=["pickups"])


class ChuyenTrangThaiRequest(BaseModel):
    """Body đẩy một yêu cầu dọc theo máy trạng thái thu gom."""

    den: str = Field(min_length=1, max_length=40)
    ghi_chu: str = Field(default="", max_length=500)


class XacNhanKhoiLuongRequest(BaseModel):
    """Body xác nhận khối lượng thật do đội vệ sinh cân."""

    weight_confirmed_kg: float = Field(ge=0)


@router.post("")
def create_pickup(payload: CreatePickupRequest, session: DbSession, user: CurrentUser) -> dict:
    """Cư dân đăng ký thu gom đồ cồng kềnh (wizard 3 bước ở spec 4.7)."""
    if user.role not in {"resident", "manager"}:
        raise forbidden("Đội vệ sinh không tạo yêu cầu thay cư dân.")
    if not payload.confirmed_no_hazardous:
        raise bad_request(
            "Bạn cần xác nhận các món trên không chứa rác nguy hại (pin, hoá chất, bóng đèn, thuốc).",
            code="PU-400",
        )

    items = [i.model_dump() for i in payload.items]
    try:
        request = pickup_service.create_pickup_request(
            session,
            resident=user,
            items=items,
            est_weight_kg=payload.est_weight_kg,
            weight_min_kg=payload.weight_min_kg,
            weight_max_kg=payload.weight_max_kg,
            preferred_date=payload.preferred_date,
            preferred_window=payload.preferred_window,
            note=payload.note,
            ngoai_lich=payload.ngoai_lich,
            # Điểm lấy hàng của riêng yêu cầu này. Ba trường đều tuỳ chọn: app cư
            # dân hiện chưa gửi, khi đó tầng dịch vụ tự lấy nơi ở của người gửi
            # (hoặc báo lỗi PU-400 nếu không có nơi ở nào cả).
            address=payload.address,
            lat=payload.lat,
            lng=payload.lng,
        )
    except ValueError as exc:
        raise bad_request(str(exc), code="PU-400") from exc

    data = pickup_dict(session, request, full=True)
    data["message_vi"] = (
        "Yêu cầu này vượt ngưỡng tự động nên cần ban quản lý duyệt."
        if request.requires_hitl
        else "Yêu cầu nằm trong ngưỡng tự động, đã được ghi nhận."
    )
    return data


@router.get("")
def list_pickups(
    session: DbSession,
    user: CurrentUser,
    status: str = "",
    building_id: int | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    """Danh sách yêu cầu. Cư dân chỉ thấy của mình."""
    statement = select(PickupRequest)
    if user.role == "resident":
        statement = statement.where(PickupRequest.resident_id == user.id)
    if status:
        try:
            trang_thai_chuan = chuan_hoa(status)
        except LoiChuyenTrangThai as exc:
            raise bad_request(f"Giá trị trạng thái '{status}' không hợp lệ.", code="PU-400") from exc
        statement = statement.where(PickupRequest.status.in_(trang_thai_tuong_duong(trang_thai_chuan)))
    if building_id is not None:
        # Lọc theo toà phải tính CẢ hai dạng cư dân: có căn hộ (PickupRequest ->
        # Unit -> Building) và chỉ gắn toà (PickupRequest -> resident.building_id,
        # unit_id = NULL). Giữ hai nhánh OR, không chỉ join Unit như đường lọc
        # duy nhất — nếu không pickup của cư dân building-only bị loại sạch.
        statement = statement.where(
            PickupRequest.unit_id.in_(select(Unit.id).where(Unit.building_id == building_id))
            | PickupRequest.resident_id.in_(select(User.id).where(User.building_id == building_id))
        )

    total = len(session.scalars(statement).all())
    rows = session.scalars(
        statement.order_by(desc(PickupRequest.created_at)).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [pickup_dict(session, r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "reject_reasons": PICKUP_REJECT_REASONS,
    }


# --- Sự cố thu gom & xác nhận hoàn thành chuyến (Gói P73) -------------------
# Các route có đoạn đường dẫn là CHỮ CỐ ĐỊNH phải khai TRƯỚC mọi route dùng
# tham số `/{request_id}` — nếu không FastAPI khớp theo thứ tự đăng ký, chuỗi
# "su-co" rơi vào `/{request_id}` và bị ép parse thành int → 422 (lỗi P84).


class BaoSuCoRequest(BaseModel):
    """Body người thu gom báo sự cố thu gom."""

    route_id: int = Field(..., gt=0)
    stop_id: int | None = Field(default=None)
    loai: str = Field(..., min_length=1, max_length=40)
    mo_ta: str = Field(default="", max_length=2000)
    anh_media_id: int | None = Field(default=None)


class XuLySuCoRequest(BaseModel):
    """Body ĐVTG xử lý một sự cố thu gom."""

    chap_nhan: bool
    ghi_chu: str = Field(default="", max_length=500)


def _su_co_dict(s: SuCoThuGom) -> dict:
    return {
        "id": s.id,
        "route_id": s.route_id,
        "stop_id": s.stop_id,
        "nguoi_bao_id": s.nguoi_bao_id,
        "loai": s.loai,
        "mo_ta": s.mo_ta,
        "anh_media_id": s.anh_media_id,
        "trang_thai": s.trang_thai,
        "nguoi_xu_ly_id": s.nguoi_xu_ly_id,
        "ghi_chu_xu_ly": s.ghi_chu_xu_ly,
        "xu_ly_luc": s.xu_ly_luc.isoformat() if s.xu_ly_luc else None,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


@router.post("/su-co")
def bao_su_co_endpoint(payload: BaoSuCoRequest, session: DbSession, user: CurrentUser) -> dict:
    """Người thu gom báo sự cố phân loại / thùng đầy / không tiếp nhận (P73)."""
    try:
        su_co = su_co_thu_gom.bao_su_co(
            session,
            nguoi_bao=user,
            route_id=payload.route_id,
            stop_id=payload.stop_id,
            loai=payload.loai,
            mo_ta=payload.mo_ta,
            anh_media_id=payload.anh_media_id,
        )
    except ValueError as exc:
        raise bad_request(str(exc), code="SUCO-400") from exc
    return _su_co_dict(su_co)


@router.get("/su-co")
def danh_sach_su_co_endpoint(
    session: DbSession,
    user: CurrentUser,
    trang_thai: str | None = None,
    route_id: int | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    """Danh sách sự cố: ĐVTG (review_pickup) thấy của đơn vị, người thu gom thấy của mình."""
    if not can(user, "review_pickup") and user.role != "cleaner":
        raise forbidden("Bạn không có quyền xem danh sách sự cố thu gom.")
    try:
        cac_su_co = su_co_thu_gom.danh_sach_su_co(
            session,
            nguoi_xem=user,
            trang_thai=trang_thai,
            route_id=route_id,
            limit=limit,
        )
    except ValueError as exc:
        raise bad_request(str(exc), code="SUCO-400") from exc
    return {"items": [_su_co_dict(s) for s in cac_su_co], "total": len(cac_su_co)}


@router.post("/su-co/{su_co_id}/xu-ly")
def xu_ly_su_co_endpoint(
    su_co_id: int,
    payload: XuLySuCoRequest,
    session: DbSession,
    user: Annotated[User, Depends(require("review_pickup"))],
) -> dict:
    """ĐVTG xử lý một sự cố thu gom (chấp nhận hoặc từ chối)."""
    try:
        su_co = su_co_thu_gom.xu_ly_su_co(
            session,
            nguoi_xu_ly=user,
            su_co_id=su_co_id,
            chap_nhan=payload.chap_nhan,
            ghi_chu=payload.ghi_chu,
        )
    except ValueError as exc:
        raise bad_request(str(exc), code="SUCO-400") from exc
    return _su_co_dict(su_co)


@router.get("/{request_id}")
def get_pickup(request_id: int, session: DbSession, user: CurrentUser) -> dict:
    """Chi tiết một yêu cầu, kèm timeline và bối cảnh ra quyết định."""
    request = session.get(PickupRequest, request_id)
    if request is None:
        raise not_found("yêu cầu thu gom này")
    if user.role == "resident" and request.resident_id != user.id:
        raise not_found("yêu cầu thu gom này")

    data = pickup_dict(session, request, full=True)
    if user.role in {"manager", "cleaner"}:
        data.update(pickup_service.decision_context(session, request))
        data["agent_suggestion"] = _agent_suggestion(session, request)
    return data


def _agent_suggestion(session, request: PickupRequest) -> dict:
    """Gợi ý gộp tuyến cho màn duyệt — khối viền nét đứt nhãn "AI đề xuất"."""
    if request.preferred_date is None:
        return {}
    cung_khung = session.scalars(
        select(PickupRequest).where(
            PickupRequest.preferred_date == request.preferred_date,
            PickupRequest.preferred_window == request.preferred_window,
            PickupRequest.status.in_(trang_thai_tuong_duong(CHO_NHAN) + trang_thai_tuong_duong(CHO_DUYET)),
            PickupRequest.id != request.id,
        )
    ).all()
    if not cung_khung:
        return {
            "label_vi": "AI đề xuất — cần người duyệt trước khi áp dụng",
            "text_vi": "Chưa có yêu cầu nào khác cùng khung giờ để gộp chuyến.",
        }
    tong = sum(r.weight_max_kg for r in cung_khung) + request.weight_max_kg
    return {
        "label_vi": "AI đề xuất — cần người duyệt trước khi áp dụng",
        "text_vi": (
            f"Gộp vào chuyến {request.preferred_window} ngày "
            f"{request.preferred_date.strftime('%d/%m')} cùng {len(cung_khung)} yêu cầu khác. "
            f"Tổng ước tính {tong:.0f} kg."
        ),
        "so_yeu_cau_gop": len(cung_khung) + 1,
        "tong_khoi_luong_kg": round(tong, 1),
    }


@router.post("/{request_id}/review")
def review_pickup(
    request_id: int,
    payload: ReviewPickupRequest,
    session: DbSession,
    user: Annotated[User, Depends(require("review_pickup"))],
) -> dict:
    """HITL #1 — ban quản lý duyệt hoặc từ chối yêu cầu vượt ngưỡng."""
    request = session.get(PickupRequest, request_id)
    if request is None:
        raise not_found("yêu cầu thu gom này")

    try:
        pickup_service.review_pickup(
            session,
            request=request,
            actor=user,
            action=payload.action,
            reason=payload.reason,
            note=payload.note,
            changes=payload.changes,
        )
    except ValueError as exc:
        raise bad_request(str(exc), code="PU-400") from exc

    write_audit(
        session,
        actor=user,
        action=f"pickup_{payload.action}",
        entity="pickup_request",
        entity_id=str(request.id),
        detail={"reason": payload.reason, "note": payload.note},
    )
    return pickup_dict(session, request, full=True)


@router.delete("/{request_id}")
def cancel_pickup(request_id: int, session: DbSession, user: CurrentUser) -> dict:
    """Cư dân huỷ yêu cầu của mình khi chưa xếp tuyến."""
    request = session.get(PickupRequest, request_id)
    if request is None:
        raise not_found("yêu cầu thu gom này")
    if request.resident_id != user.id and user.role != "manager":
        raise forbidden("Bạn chỉ huỷ được yêu cầu của chính mình.")

    try:
        pickup_service.cancel_pickup(session, request=request, actor=user)
    except ValueError as exc:
        raise bad_request(str(exc), code="PU-409") from exc
    return pickup_dict(session, request, full=True)


@router.post("/{request_id}/chuyen-trang-thai")
def chuyen_trang_thai_pickup(
    request_id: int,
    payload: ChuyenTrangThaiRequest,
    session: DbSession,
    user: Annotated[User, Depends(require("complete_stop"))],
) -> dict:
    """Đội vệ sinh đẩy một yêu cầu dọc theo máy trạng thái thu gom."""
    request = session.get(PickupRequest, request_id)
    if request is None:
        raise not_found("yêu cầu thu gom này")

    try:
        pickup_flow.chuyen_trang_thai_yeu_cau(
            session,
            request=request,
            den=payload.den,
            actor=user,
            ghi_chu=payload.ghi_chu,
        )
    except ValueError as exc:
        raise bad_request(str(exc), code="PU-400") from exc

    write_audit(
        session,
        actor=user,
        action=f"pickup_chuyen_trang_thai_{payload.den}",
        entity="pickup_request",
        entity_id=str(request.id),
        detail={"den": payload.den, "ghi_chu": payload.ghi_chu},
    )
    return pickup_dict(session, request, full=True)


@router.post("/{request_id}/xac-nhan-khoi-luong")
def xac_nhan_khoi_luong_pickup(
    request_id: int,
    payload: XacNhanKhoiLuongRequest,
    session: DbSession,
    user: Annotated[User, Depends(require("complete_stop"))],
) -> dict:
    """Đội vệ sinh xác nhận khối lượng THẬT — điểm chỉ trao từ con số này."""
    request = session.get(PickupRequest, request_id)
    if request is None:
        raise not_found("yêu cầu thu gom này")

    try:
        pickup_flow.xac_nhan_khoi_luong(
            session,
            request=request,
            weight_confirmed_kg=payload.weight_confirmed_kg,
            actor=user,
        )
    except ValueError as exc:
        raise bad_request(str(exc), code="PU-400") from exc

    write_audit(
        session,
        actor=user,
        action="pickup_xac_nhan_khoi_luong",
        entity="pickup_request",
        entity_id=str(request.id),
        detail={"weight_confirmed_kg": payload.weight_confirmed_kg},
    )
    return pickup_dict(session, request, full=True)


@router.post("/routes/{route_id}/xac-nhan")
def xac_nhan_chuyen_endpoint(
    route_id: int,
    session: DbSession,
    user: Annotated[User, Depends(require("review_route"))],
) -> dict:
    """ĐVTG xác nhận hoàn thành chuyến đã đi hết điểm dừng (P73)."""
    try:
        route = su_co_thu_gom.xac_nhan_hoan_thanh_chuyen(
            session,
            nguoi_xac_nhan=user,
            route_id=route_id,
        )
    except ValueError as exc:
        raise bad_request(str(exc), code="SUCO-400") from exc
    return {
        "id": route.id,
        "status": route.status,
        "xac_nhan_boi": route.xac_nhan_boi,
        "xac_nhan_luc": route.xac_nhan_luc.isoformat() if route.xac_nhan_luc else None,
    }
