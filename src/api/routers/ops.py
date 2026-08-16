"""Vận hành, trace agent, chất lượng AI và cảnh báo — khu vực của ban quản lý."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, desc, func, select

from src.agents.graph import GRAPH_SHAPE
from src.api.deps import CurrentUser, DbSession, require
from src.api.errors import bad_request, not_found
from src.config import get_settings
from src.db.models import AgentRun, Alert, Bin, Notification, RunNodeMetric, User
from src.services import metrics
from src.services import reporting as reporting_service
from src.services import runs as runs_service

router = APIRouter(tags=["ops"])


def _khoi_co_che(session: DbSession) -> dict:
    """Ba cơ chế vừa thêm — trạng thái THẬT để trang Vận hành nói thật.

    Không bao giờ trả giá trị bí mật: chỉ cờ bật/tắt và con số đếm. Thùng "chưa
    cấp khoá" là ``device_key_hash == ''`` (mặc định của cột), không phải NULL.
    """
    cau_hinh = get_settings()
    tong_thung, so_khoa_rieng = session.execute(
        select(
            func.count(Bin.id),
            func.count(case((Bin.device_key_hash != "", 1), else_=None)),
        )
    ).one()
    return {
        "rate_limit_dang_ky": {
            "bat": cau_hinh.register_rate_limit > 0,
            "so_lan": cau_hinh.register_rate_limit,
            "cua_so_giay": cau_hinh.register_rate_window_seconds,
        },
        "khoa_thiet_bi": {
            "so_thung_khoa_rieng": int(so_khoa_rieng or 0),
            "tong_thung": int(tong_thung or 0),
        },
        "duong_di_that": {
            "bat": bool(cau_hinh.route_real_distance),
            "dich_vu": "OSRM",
        },
    }


@router.get("/runs")
def list_runs(
    session: DbSession,
    user: Annotated[User, Depends(require("view_runs"))],
    kind: str = "",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    statement = select(AgentRun)
    if kind:
        statement = statement.where(AgentRun.kind == kind)
    total = len(session.scalars(statement).all())
    rows = session.scalars(
        statement.order_by(desc(AgentRun.started_at)).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [
            {
                "id": r.id,
                "kind": r.kind,
                "trigger": r.trigger,
                "status": r.status,
                "items_processed": r.items_processed,
                "duration_ms": r.duration_ms,
                "total_cost_usd": r.total_cost_usd,
                "started_at": r.started_at.isoformat(),
                "is_seed": r.is_seed,
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "graph": GRAPH_SHAPE,
    }


@router.get("/runs/{run_id}")
def get_run(
    run_id: int,
    session: DbSession,
    user: Annotated[User, Depends(require("view_runs"))],
) -> dict:
    """Chi tiết một lần chạy — timeline các node cho màn 4.15."""
    run = session.get(AgentRun, run_id)
    if run is None:
        raise not_found("lần chạy này")
    nodes = session.scalars(select(RunNodeMetric).where(RunNodeMetric.run_id == run.id).order_by(RunNodeMetric.id)).all()
    data = runs_service.run_to_dict(run, nodes)
    data["graph"] = GRAPH_SHAPE
    # Đường đã đi, để UI tô đậm và làm mờ nhánh không đi.
    data["path"] = [n.node for n in nodes if n.status != "skipped"]
    return data


@router.get("/ops/metrics")
def ops_metrics(
    session: DbSession,
    user: Annotated[User, Depends(require("view_ops"))],
    days: int = Query(default=30, ge=1, le=365),
) -> dict:
    """Chi phí, độ trễ, lỗi, định tuyến — ba khối của trang Vận hành."""
    ket_qua = metrics.ops_metrics(session, days=days)
    ket_qua["co_che"] = _khoi_co_che(session)
    return ket_qua


@router.get("/eval/summary")
def eval_summary(
    session: DbSession,
    user: Annotated[User, Depends(require("view_eval"))],
) -> dict:
    """Trang Chất lượng AI, kèm chỉ số an toàn cốt lõi."""
    return metrics.eval_summary(session)


@router.get("/overview")
def overview(
    session: DbSession,
    user: Annotated[User, Depends(require("view_ops"))],
    building_id: int | None = None,
) -> dict:
    """Màn Tổng quan của ban quản lý."""
    ket_qua = metrics.manager_overview(session, building_id=building_id)
    ket_qua["co_che"] = _khoi_co_che(session)
    return ket_qua


@router.get("/bao-cao-tuan-thu")
def bao_cao_tuan_thu(
    session: DbSession,
    user: Annotated[User, Depends(require("view_ops"))],
    thang: str = Query(default="", min_length=7, max_length=7),
) -> dict:
    """Báo cáo tuân thủ theo tháng — định dạng ``YYYY-MM``.

    Một tháng không có dữ liệu trả về báo cáo toàn số 0, không phải 404.
    """
    try:
        return reporting_service.bao_cao_tuan_thu(session, thang)
    except ValueError as exc:
        raise bad_request(str(exc), code="REPORT-400") from exc


@router.get("/alerts")
def list_alerts(
    session: DbSession,
    user: Annotated[User, Depends(require("view_ops"))],
    only_open: bool = True,
) -> dict:
    statement = select(Alert)
    if only_open:
        statement = statement.where(Alert.ack.is_(False))
    rows = session.scalars(statement.order_by(desc(Alert.triggered_at))).all()
    return {
        "items": [
            {
                "id": a.id,
                "severity": a.severity,
                "title": a.title,
                "building_id": a.building_id,
                "entity": a.entity,
                "entity_id": a.entity_id,
                "threshold": a.threshold,
                "ack": a.ack,
                "is_seed": a.is_seed,
                "triggered_at": a.triggered_at.isoformat(),
            }
            for a in rows
        ]
    }


@router.post("/alerts/{alert_id}/ack")
def ack_alert(
    alert_id: int,
    session: DbSession,
    user: Annotated[User, Depends(require("view_ops"))],
) -> dict:
    alert = session.get(Alert, alert_id)
    if alert is None:
        raise not_found("cảnh báo này")
    alert.ack = True
    alert.ack_by = user.id
    session.flush()
    return {"ok": True}


@router.get("/notifications")
def list_notifications(session: DbSession, user: CurrentUser) -> dict:
    """Thông báo của chính người đang đăng nhập."""
    rows = session.scalars(
        select(Notification).where(Notification.user_id == user.id).order_by(desc(Notification.created_at)).limit(50)
    ).all()
    return {
        "items": [
            {
                "id": n.id,
                "title": n.title,
                "body": n.body,
                "entity": n.entity,
                "entity_id": n.entity_id,
                "read": n.read_at is not None,
                "created_at": n.created_at.isoformat(),
            }
            for n in rows
        ],
        "unread": sum(1 for n in rows if n.read_at is None),
    }
