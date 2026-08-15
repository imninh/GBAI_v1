"""Tuyến thu gom — HITL #3, màn ăn điểm cao nhất theo spec 4.12."""

from __future__ import annotations

from datetime import date as date_type
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select

from src.api.deps import CurrentUser, DbSession, require
from src.api.errors import bad_request, not_found
from src.api.serializers import route_dict
from src.db.models import PickupRoute, RouteStop, User
from src.models.schemas import CompleteStopRequest, ProposeRouteRequest, ReviewRouteRequest
from src.services import duong_di_that, route_planner, runs
from src.services.auth import write_audit
from src.services.classifier import NodeMetric
from src.services.pickup_lifecycle import CHO_NHAN, DA_NHAN, chuan_hoa

router = APIRouter(prefix="/routes", tags=["routes"])


class DuongDiRequest(BaseModel):
    """Các điểm cần nối, theo thứ tự (mốc của cư dân → điểm gửi)."""

    diem: list[dict]


@router.post("/duong-di")
def duong_di_toi_diem(payload: DuongDiRequest, user: CurrentUser) -> dict:
    """Hình đường đi thật nối các điểm cư dân chọn.

    Trả ``{"duong_di": [[lat,lng]…] | null}``. ``null`` = OSRM tắt/hỏng/hết giờ
    → client vẽ đường thẳng như cũ. Không đụng CSDL, chỉ hỏi dịch vụ định tuyến.
    """
    toa_do = [
        (float(d["lat"]), float(d["lng"]))
        for d in payload.diem
        if d.get("lat") is not None and d.get("lng") is not None
    ]
    if len(toa_do) < 2:
        return {"duong_di": None}
    hinh = duong_di_that.hinh_duong_di(toa_do)
    return {"duong_di": [[lat, lng] for lat, lng in hinh] if hinh else None}


def _duong_di_tu_stops(cac_diem: list[dict]) -> list[list[float]] | None:
    """Hình đường đi thật theo đúng thứ tự ``seq``, từ dữ liệu điểm dừng đã seri hoá.

    Trả về ``None`` khi chưa đủ 2 toạ độ hoặc ``hinh_duong_di`` không tính được
    (cờ tắt / hỏng / quá hạn). Khoá vẫn luôn được thêm vào payload — frontend
    phân biệt "chưa tính được" với "không có trường này" dễ hơn.
    """
    toa_do = [
        (float(diem["lat"]), float(diem["lng"]))
        for diem in cac_diem
        if diem.get("lat") is not None and diem.get("lng") is not None
    ]
    if len(toa_do) < 2:
        return None
    hinh = duong_di_that.hinh_duong_di(toa_do)
    if hinh is None:
        return None
    return [[lat, lng] for lat, lng in hinh]


@router.post("/propose")
def propose_route(
    payload: ProposeRouteRequest,
    session: DbSession,
    user: Annotated[User, Depends(require("review_route"))],
) -> dict:
    """Agent gộp các yêu cầu đã duyệt thành một tuyến đề xuất.

    Kết quả luôn ở trạng thái ``proposed``: **agent không được tự đổi lịch làm
    việc của con người.**
    """
    run = runs.start_run(session, kind="schedule", trigger="manager")
    try:
        route = route_planner.propose_route(
            session,
            service_date=payload.service_date,
            window=payload.window,
            team_id=payload.team_id,
            capacity_kg=payload.capacity_kg,
            run_id=run.id,
        )
    except ValueError as exc:
        runs.finish_run(
            session,
            run,
            nodes=[NodeMetric(node="propose_route", status="error", error_type="NO_CANDIDATE")],
            items_processed=0,
            error=str(exc),
        )
        raise bad_request(str(exc), code="ROUTE-404") from exc

    runs.finish_run(
        session,
        run,
        nodes=[
            NodeMetric(
                node="propose_route",
                meta={
                    "so_diem_dung": len(route.stops),
                    "tong_khoi_luong_kg": route.total_weight_kg,
                    "km_uoc_tinh": route.est_distance_km,
                    "km_neu_di_le": route.reasoning.get("baseline_km"),
                },
            )
        ],
        items_processed=len(route.stops),
    )
    return route_dict(session, route, full=True)


@router.get("")
def list_routes(
    session: DbSession,
    user: CurrentUser,
    service_date: date_type | None = None,
    status: str = "",
) -> dict:
    """Danh sách tuyến. Đội vệ sinh chỉ thấy tuyến của mình."""
    statement = select(PickupRoute)
    if service_date is not None:
        statement = statement.where(PickupRoute.service_date == service_date)
    if status:
        statement = statement.where(PickupRoute.status == status)
    if user.role == "cleaner":
        statement = statement.where(PickupRoute.team_id == user.id, PickupRoute.status != "proposed")

    rows = session.scalars(statement.order_by(PickupRoute.service_date.desc())).all()
    return {"items": [route_dict(session, r) for r in rows]}


@router.get("/{route_id}")
def get_route(route_id: int, session: DbSession, user: CurrentUser) -> dict:
    """Chi tiết tuyến kèm khối "vì sao gộp thế này" và diff so với bản AI đề xuất."""
    route = session.get(PickupRoute, route_id)
    if route is None:
        raise not_found("tuyến này")
    if user.role == "cleaner" and route.team_id != user.id:
        raise not_found("tuyến này")

    data = route_dict(session, route, full=True)
    data["diff"] = route_planner.route_diff(route)
    data["duong_di"] = _duong_di_tu_stops(data.get("stops", []))
    return data


@router.post("/{route_id}/review")
def review_route(
    route_id: int,
    payload: ReviewRouteRequest,
    session: DbSession,
    user: Annotated[User, Depends(require("review_route"))],
) -> dict:
    """HITL #3 — đội trưởng duyệt / sửa rồi duyệt / đề xuất lại / huỷ."""
    route = session.get(PickupRoute, route_id)
    if route is None:
        raise not_found("tuyến này")

    if payload.action == "regenerate":
        route.status = "cancelled"
        for stop in route.stops:
            request = route_planner.yeu_cau_cua(session, stop)
            if request is not None and chuan_hoa(request.status) == DA_NHAN:
                request.status = CHO_NHAN
        session.flush()
        try:
            moi = route_planner.propose_route(
                session,
                service_date=route.service_date,
                window=route.window,
                team_id=route.team_id,
            )
        except ValueError as exc:
            raise bad_request(str(exc), code="ROUTE-404") from exc
        return route_dict(session, moi, full=True)

    try:
        route_planner.review_route(
            session,
            route=route,
            actor=user,
            action=payload.action,
            stop_order=payload.stop_order,
            removed_stops=payload.removed_stops,
        )
    except ValueError as exc:
        raise bad_request(str(exc), code="ROUTE-400") from exc

    write_audit(
        session,
        actor=user,
        action=f"route_{payload.action}",
        entity="pickup_route",
        entity_id=str(route.id),
        detail={"removed_stops": payload.removed_stops or [], "stop_order": payload.stop_order or []},
    )

    data = route_dict(session, route, full=True)
    data["diff"] = route_planner.route_diff(route)
    data["duong_di"] = _duong_di_tu_stops(data.get("stops", []))
    data["message_vi"] = (
        f"Đã thông báo cho {len(route.stops)} cư dân" + (" và tổ vệ sinh." if route.team_id else ".")
        if payload.action != "cancel"
        else "Đã huỷ tuyến, các yêu cầu quay về nhóm chờ xếp tuyến."
    )
    return data


@router.post("/{route_id}/stops/{stop_id}/done")
def complete_stop(
    route_id: int,
    stop_id: int,
    payload: CompleteStopRequest,
    session: DbSession,
    user: Annotated[User, Depends(require("complete_stop"))],
) -> dict:
    """Đội vệ sinh đánh dấu đã thu tại một điểm dừng."""
    stop = session.get(RouteStop, stop_id)
    if stop is None or stop.route_id != route_id:
        raise not_found("điểm dừng này")

    try:
        route_planner.complete_stop(
            session,
            stop=stop,
            actor=user,
            issue=payload.issue,
            issue_note=payload.issue_note,
            actual_weight_kg=payload.actual_weight_kg,
        )
    except ValueError as exc:
        raise bad_request(str(exc), code="ROUTE-400") from exc

    # Báo có rác nguy hại lẫn vào là sự cố an toàn — tạo cảnh báo cho BQL ngay.
    if payload.issue == "co_rac_nguy_hai":
        from src.db.models import Alert, Unit

        request = route_planner.yeu_cau_cua(session, stop)
        unit = session.get(Unit, request.unit_id) if request else None
        session.add(
            Alert(
                severity="critical",
                title=(
                    f"Đội vệ sinh báo có rác nguy hại lẫn trong yêu cầu #{stop.request_id}"
                    + (f" tại {unit.code}" if unit else "")
                ),
                building_id=unit.building_id if unit else None,
                entity="pickup_request",
                entity_id=str(stop.request_id),
                threshold="Báo từ hiện trường",
            )
        )
        session.flush()

    route = session.get(PickupRoute, route_id)
    return route_dict(session, route, full=True)
