"""Tuyến thu gom — HITL #3, màn ăn điểm cao nhất theo spec 4.12."""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import exists, or_, select

from src.api.deps import CurrentUser, DbSession, require
from src.api.errors import bad_request, not_found
from src.api.serializers import route_dict
from src.db.models import PickupRoute, RouteStop, RouteThanhVien, User
from src.models.schemas import CompleteStopRequest, ProposeRouteRequest, ReviewRouteRequest
from src.services import duong_di_that, kip_thu_gom, lich_tu_dong, route_planner, runs
from src.services.auth import write_audit
from src.services.classifier import NodeMetric
from src.services.pickup_lifecycle import CHO_NHAN, DA_NHAN, chuan_hoa

router = APIRouter(prefix="/routes", tags=["routes"])


def _lo_trinh_tu_stops(cac_diem: list[dict]) -> tuple[list[list[float]] | None, dict | None]:
    """Hình đường đi thật và metadata lộ trình từ dữ liệu điểm dừng đã seri hoá.

    Trả về (duong_di, lo_trinh_meta) hoặc (None, None) khi không tính được.
    """
    toa_do = [
        (float(diem["lat"]), float(diem["lng"]))
        for diem in cac_diem
        if diem.get("lat") is not None and diem.get("lng") is not None
    ]
    if len(toa_do) < 2:
        return None, None
    lt = duong_di_that.lo_trinh(toa_do)
    if lt is None:
        return None, None

    duong_di = [[lat, lng] for lat, lng in lt.polyline]
    meta = {
        "total_km": lt.total_km,
        "total_minutes": lt.total_minutes,
        "legs": [
            {
                "from_seq": cac_diem[i].get("seq", i + 1) if i < len(cac_diem) else i + 1,
                "to_seq": cac_diem[i + 1].get("seq", i + 2) if i + 1 < len(cac_diem) else i + 2,
                "distance_km": leg.distance_km,
                "duration_minutes": leg.duration_minutes,
            }
            for i, leg in enumerate(lt.legs)
        ],
    }
    return duong_di, meta


def _duong_di_tu_stops(cac_diem: list[dict]) -> list[list[float]] | None:
    """Hình đường đi thật theo đúng thứ tự ``seq`` (backward compatible)."""
    dd, _ = _lo_trinh_tu_stops(cac_diem)
    return dd


# ========================================================================
#  ROUTE LITERAL — phải đứng TRƯỚC mọi route bắt đầu bằng /{route_id}
# ========================================================================


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


@router.post("/propose-multi")
def propose_routes(
    payload: ProposeRouteRequest,
    session: DbSession,
    user: Annotated[User, Depends(require("review_route"))],
) -> dict:
    """Agent gộp các yêu cầu đã duyệt thành một hoặc nhiều tuyến đề xuất."""
    run = runs.start_run(session, kind="schedule", trigger="manager")
    try:
        routes = route_planner.propose_routes(
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
            nodes=[NodeMetric(node="propose_routes", status="error", error_type="NO_CANDIDATE")],
            items_processed=0,
            error=str(exc),
        )
        raise bad_request(str(exc), code="ROUTE-404") from exc

    total_stops = sum(len(r.stops) for r in routes)
    runs.finish_run(
        session,
        run,
        nodes=[
            NodeMetric(
                node="propose_routes",
                meta={
                    "so_tuyen": len(routes),
                    "so_diem_dung": total_stops,
                },
            )
        ],
        items_processed=total_stops,
    )
    return {"items": [route_dict(session, r, full=True) for r in routes]}


class TuDongTaoRequest(BaseModel):
    """Tham số cho lần chạy cron tự tạo chuyến (gói P72)."""

    truoc_bao_lau_phut: int = 60
    bay_gio: datetime | None = None


@router.post("/tu-dong-tao")
def tu_dong_tao(
    payload: TuDongTaoRequest,
    session: DbSession,
    user: Annotated[User, Depends(require("review_route"))],
) -> dict:
    """Cron ngoài (Railway Cron Job) gọi định kỳ: tự tạo chuyến theo lịch cố định.

    Một tiếng trước giờ thu gom, hệ thống kiểm các điểm cần thu gom, gộp thành
    chuyến đề xuất (``status="proposed"``) và giao ``nguon_tao="tu_dong"``. Bảng
    tóm tắt trả về giúp nhìn log cron là biết lượt chạy vừa làm gì.
    """
    run = runs.start_run(session, kind="schedule", trigger="cron")
    bay_gio = payload.bay_gio or datetime.now()
    try:
        ket_qua = lich_tu_dong.tao_chuyen_tu_lich(
            session,
            bay_gio=bay_gio,
            truoc_bao_lau_phut=payload.truoc_bao_lau_phut,
            run_id=run.id,
        )
    except Exception as exc:
        runs.finish_run(
            session,
            run,
            nodes=[NodeMetric(node="tao_chuyen_tu_lich", status="error", error_type="SCHEDULE_ERROR")],
            items_processed=0,
            error=str(exc),
        )
        raise
    runs.finish_run(
        session,
        run,
        nodes=[NodeMetric(node="tao_chuyen_tu_lich", meta=ket_qua)],
        items_processed=ket_qua.get("so_chuyen_tao", 0),
    )
    return ket_qua


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
        # Hai đường nhìn thấy chuyến: trưởng kíp qua ``team_id``, thành viên kíp
        # qua ``RouteThanhVien``. Trước đây chỉ trưởng kíp nhìn thấy — một kíp ba
        # người thì hai người kia không bao giờ thấy tuyến của mình (E2E §8).
        trong_kip = exists(
            select(RouteThanhVien.route_id).where(
                RouteThanhVien.route_id == PickupRoute.id,
                RouteThanhVien.user_id == user.id,
            )
        )
        statement = statement.where(
            or_(PickupRoute.team_id == user.id, trong_kip),
            PickupRoute.status != "proposed",
        )

    rows = session.scalars(statement.order_by(PickupRoute.service_date.desc())).all()
    return {"items": [route_dict(session, r) for r in rows]}


class TaoLichTuanRequest(BaseModel):
    """Tham số cho lệnh lên lịch cả tuần (gói P80)."""

    tuan_bat_dau: date_type


class GanKipRequest(BaseModel):
    """Gán kíp cho một chuyến (gói P80)."""

    user_ids: list[int]
    truong_kip_id: int | None = None


@router.post("/tao-lich-tuan")
def tao_lich_tuan_endpoint(
    payload: TaoLichTuanRequest,
    session: DbSession,
    user: Annotated[User, Depends(require("review_route"))],
) -> dict:
    """Gọi một lần đầu tuần: tạo chuyến cho 7 ngày + gán kíp theo vòng tròn."""
    run = runs.start_run(session, kind="schedule", trigger="cron")
    try:
        ket_qua = lich_tu_dong.tao_lich_tuan(
            session,
            actor=user,
            tuan_bat_dau=payload.tuan_bat_dau,
            run_id=run.id,
        )
    except Exception as exc:
        runs.finish_run(
            session,
            run,
            nodes=[NodeMetric(node="tao_lich_tuan", status="error", error_type="SCHEDULE_ERROR")],
            items_processed=0,
            error=str(exc),
        )
        raise
    runs.finish_run(
        session,
        run,
        nodes=[NodeMetric(node="tao_lich_tuan", meta=ket_qua)],
        items_processed=ket_qua.get("so_chuyen_tao", 0),
    )
    return ket_qua


@router.get("/nhan-vien-kha-dung")
def nhan_vien_kha_dung_endpoint(
    session: DbSession,
    user: Annotated[User, Depends(require("review_route"))],
) -> dict:
    """Danh sách nhân viên thu gom đang hoạt động (để xếp kíp)."""
    ds = kip_thu_gom.nhan_vien_kha_dung(session)
    return {"items": [{"id": u.id, "full_name": u.full_name, "role": u.role} for u in ds]}


class DuongDiRequest(BaseModel):
    """Các điểm cần nối, theo thứ tự (mốc của cư dân → điểm gửi)."""

    diem: list[dict]


@router.post("/duong-di")
def duong_di_toi_diem(payload: DuongDiRequest, user: CurrentUser) -> dict:
    """Hình đường đi thật nối các điểm cư dân chọn (mốc → điểm gửi).

    Trả ``{"duong_di": [[lat,lng]…] | null}``. ``null`` = OSRM tắt/hỏng/hết giờ →
    client vẽ đường thẳng như cũ. Không đụng CSDL, chỉ hỏi dịch vụ định tuyến.
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


class NavigateRequest(BaseModel):
    """Toạ độ xuất phát và điểm đến cho dẫn đường in-app."""

    origin_lat: float
    origin_lng: float
    dest_lat: float
    dest_lng: float


@router.post("/navigate")
def navigate(payload: NavigateRequest, user: CurrentUser) -> dict:
    """Trả polyline + khoảng cách + thời gian từ vị trí hiện tại → điểm thu gom."""
    origin = (payload.origin_lat, payload.origin_lng)
    dest = (payload.dest_lat, payload.dest_lng)
    dd = duong_di_that.dan_duong(origin, dest)

    if dd is not None:
        return {
            "polyline": [[lat, lng] for lat, lng in dd.polyline],
            "distance_km": dd.distance_km,
            "duration_minutes": dd.duration_minutes,
        }

    # Fallback khi OSRM tắt hoặc lỗi mạng: đường chim bay
    from src.services.vrp_solver import haversine_km

    dist = round(haversine_km(origin[0], origin[1], dest[0], dest[1]), 2)
    dur = round((dist / 30.0) * 60.0, 1)
    return {
        "polyline": [[origin[0], origin[1]], [dest[0], dest[1]]],
        "distance_km": dist,
        "duration_minutes": dur,
    }


# ========================================================================
#  ROUTE THAM SỐ — phải đứng SAU mọi route literal
# ========================================================================


@router.get("/{route_id}")
def get_route(route_id: int, session: DbSession, user: CurrentUser) -> dict:
    """Chi tiết tuyến kèm khối "vì sao gộp thế này" và diff so với bản AI đề xuất."""
    route = session.get(PickupRoute, route_id)
    if route is None:
        raise not_found("tuyến này")
    if user.role == "cleaner":
        la_truong_kip = route.team_id == user.id
        trong_kip = (
            session.scalar(
                select(RouteThanhVien.id).where(
                    RouteThanhVien.route_id == route.id,
                    RouteThanhVien.user_id == user.id,
                )
            )
            is not None
        )
        if not (la_truong_kip or trong_kip):
            # 404 chứ không 403 — không lộ sự tồn tại của tuyến với kíp khác.
            raise not_found("tuyến này")

    data = route_dict(session, route, full=True)
    data["diff"] = route_planner.route_diff(route)
    duong_di, lo_trinh_meta = _lo_trinh_tu_stops(data.get("stops", []))
    data["duong_di"] = duong_di
    data["lo_trinh_meta"] = lo_trinh_meta
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
    duong_di, lo_trinh_meta = _lo_trinh_tu_stops(data.get("stops", []))
    data["duong_di"] = duong_di
    data["lo_trinh_meta"] = lo_trinh_meta
    data["message_vi"] = (
        f"Đã thông báo cho {len(route.stops)} cư dân" + (" và tổ vệ sinh." if route.team_id else ".")
        if payload.action != "cancel"
        else "Đã huỷ tuyến, các yêu cầu quay về nhóm chờ xếp tuyến."
    )
    return data


class KhongCoNguoiRequest(BaseModel):
    """Lý do đánh dấu thùng ĐẦY khi không tìm được người vận chuyển (gói P72)."""

    ly_do: str = ""


@router.post("/{route_id}/khong-co-nguoi")
def khong_co_nguoi(
    route_id: int,
    payload: KhongCoNguoiRequest,
    session: DbSession,
    user: Annotated[User, Depends(require("review_route"))],
) -> dict:
    """Không tìm được người vận chuyển → đánh dấu thùng của chuyến là ĐẦY.

    Cờ chỉ ảnh hưởng tới cái người dùng nhìn thấy — điểm vẫn thu gom theo lịch
    cố định. Không ghi đè số đo cảm biến của thùng.
    """
    run = runs.start_run(session, kind="schedule", trigger="manager")
    try:
        so_thung = lich_tu_dong.danh_dau_day_khi_khong_co_nguoi(
            session,
            actor=user,
            route_id=route_id,
            ly_do=payload.ly_do,
        )
    except ValueError as exc:
        runs.finish_run(
            session,
            run,
            nodes=[NodeMetric(node="danh_dau_day", status="error", error_type="ROUTE_NOT_FOUND")],
            items_processed=0,
            error=str(exc),
        )
        raise bad_request(str(exc), code="ROUTE-404") from exc
    runs.finish_run(
        session,
        run,
        nodes=[NodeMetric(node="danh_dau_day", meta={"so_thung": so_thung})],
        items_processed=so_thung,
    )
    return {
        "status": "ok",
        "route_id": route_id,
        "so_thung_danh_dau": so_thung,
        "message_vi": "Đã đánh dấu thùng là ĐẦY; điểm vẫn thu gom theo lịch cố định.",
    }


@router.get("/{route_id}/kip")
def get_kip(
    route_id: int,
    session: DbSession,
    user: Annotated[User, Depends(require("review_route"))],
) -> dict:
    """Thành viên kíp của chuyến. Không trả số điện thoại, không trả email."""
    route = session.get(PickupRoute, route_id)
    if route is None:
        raise not_found("tuyến này")
    return {"items": kip_thu_gom.kip_cua_chuyen(session, route_id=route_id)}


@router.put("/{route_id}/kip")
def put_kip(
    route_id: int,
    payload: GanKipRequest,
    session: DbSession,
    user: Annotated[User, Depends(require("review_route"))],
) -> dict:
    """Gán hoặc gán lại kíp cho chuyến — phần \"chỉnh sửa\" mà người duyệt yêu cầu."""
    route = session.get(PickupRoute, route_id)
    if route is None:
        raise not_found("tuyến này")
    return kip_thu_gom.gan_kip(
        session,
        actor=user,
        route_id=route_id,
        user_ids=payload.user_ids,
        truong_kip_id=payload.truong_kip_id,
    )


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
