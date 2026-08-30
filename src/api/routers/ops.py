"""Vận hành, trace agent, chất lượng AI và cảnh báo — khu vực của ban quản lý."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import case, desc, func, select

from src.agents.graph import GRAPH_SHAPE
from src.api.deps import CurrentUser, DbSession, require
from src.api.errors import bad_request, not_found
from src.config import get_settings
from src.db.models import AgentRun, Alert, Bin, Notification, RunNodeMetric, User
from src.services import batch_gan_nhan as batch_service
from src.services import metrics
from src.services import reporting as reporting_service
from src.services import runs as runs_service

router = APIRouter(tags=["ops"])


class QuetBatchBody(BaseModel):
    """Body cho ``POST /ops/batch/quet`` — khoảng ngày quét (ISO date)."""

    tu_ngay: str | None = None
    den_ngay: str | None = None
    gioi_han: int = 500


class TaoBatchBody(BaseModel):
    """Body cho ``POST /ops/batch`` — ngày đứng tên lô, bắt buộc truyền vào."""

    ngay: str
    nguon: str = "hon_hop"
    so_anh_toi_da: int = 200
    ghi_chu: str = ""


class DongBatchBody(BaseModel):
    """Body cho ``POST /ops/batch/{batch_id}/dong`` — thời điểm đóng (ISO)."""

    dong_luc: str | None = None


class DocThongBaoBody(BaseModel):
    """Body cho ``POST /notifications/read`` — danh sách id đọc, ``None`` = đọc hết."""

    ids: list[int] | None = None


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


@router.get("/insights/trend")
def trend(
    session: DbSession,
    user: Annotated[User, Depends(require("view_ops"))],
    days: int = Query(default=7),
) -> dict:
    """Chuỗi thời gian cho biểu đồ xu hướng phân loại & thu gom (mỗi ngày).

    ``days`` bị kẹp vào [1, 90] để không ai ép server quét cả lịch sử — vượt
    giới hạn thì trả số ngày đã kẹp, không lỗi.
    """
    days = max(1, min(90, days))
    return {"items": metrics.trend_metrics(session, days=days)}


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


@router.post("/notifications/read")
def doc_thong_bao(body: DocThongBaoBody, session: DbSession, user: CurrentUser) -> dict:
    """Đánh dấu thông báo đã đọc.

    Chỉ được đánh dấu **thông báo của chính user** — truyền id của người khác thì
    dòng đó bị bỏ qua, không lỗi. ``ids = null`` đánh dấu đọc hết.
    """
    statement = select(Notification).where(Notification.user_id == user.id)
    if body.ids:
        statement = statement.where(Notification.id.in_(body.ids))
    rows = session.scalars(statement).all()
    for n in rows:
        if n.read_at is None:
            n.read_at = datetime.now(UTC)
    session.flush()
    return {"ok": True}


# --- Gom ảnh lỗi thành lô gán nhãn (gói P74) ------------------------------


@router.post("/ops/batch/quet")
def ops_batch_quet(
    body: QuetBatchBody,
    session: DbSession,
    user: Annotated[User, Depends(require("view_ops"))],
) -> dict:
    """Quét ảnh lỗi, đánh dấu ``can_gan_nhan = True``."""
    tu = date.fromisoformat(body.tu_ngay) if body.tu_ngay else None
    den = date.fromisoformat(body.den_ngay) if body.den_ngay else None
    return batch_service.quet_anh_can_gan_nhan(
        session, tu_ngay=tu, den_ngay=den, gioi_han=body.gioi_han
    )


@router.post("/ops/batch")
def ops_tao_batch(
    body: TaoBatchBody,
    session: DbSession,
    user: Annotated[User, Depends(require("view_ops"))],
) -> dict:
    """Tạo lô từ ảnh đã đánh dấu. Không có ảnh → 400, không tạo lô rỗng."""
    batch = batch_service.tao_batch(
        session,
        actor=user,
        ngay=date.fromisoformat(body.ngay),
        nguon=body.nguon,
        so_anh_toi_da=body.so_anh_toi_da,
        ghi_chu=body.ghi_chu,
    )
    if batch is None:
        raise bad_request("Không có ảnh nào cần gán nhãn để tạo lô", code="BATCH-EMPTY")
    return {
        "id": batch.id,
        "ma": batch.ma,
        "trang_thai": batch.trang_thai,
        "nguon": batch.nguon,
        "so_anh": batch.so_anh,
    }


@router.post("/ops/batch/{batch_id}/dong")
def ops_dong_batch(
    batch_id: int,
    body: DongBatchBody,
    session: DbSession,
    user: Annotated[User, Depends(require("view_ops"))],
) -> dict:
    """Đóng lô: ``mo`` → ``dong``. Đóng lần hai → 400."""
    dong_luc = datetime.fromisoformat(body.dong_luc) if body.dong_luc else None
    try:
        batch = batch_service.dong_batch(
            session, actor=user, batch_id=batch_id, dong_luc=dong_luc
        )
    except ValueError as exc:
        raise bad_request(str(exc), code="BATCH-400") from exc
    return {
        "id": batch.id,
        "ma": batch.ma,
        "trang_thai": batch.trang_thai,
        "dong_luc": batch.dong_luc.isoformat() if batch.dong_luc else None,
    }


@router.get("/ops/batch")
def ops_danh_sach_batch(
    session: DbSession,
    user: Annotated[User, Depends(require("view_ops"))],
    trang_thai: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> dict:
    """Danh sách lô, mới nhất trước."""
    batches = batch_service.danh_sach_batch(session, trang_thai=trang_thai, limit=limit)
    return {
        "items": [
            {
                "id": b.id,
                "ma": b.ma,
                "trang_thai": b.trang_thai,
                "nguon": b.nguon,
                "so_anh": b.so_anh,
                "created_at": b.created_at.isoformat() if b.created_at else None,
            }
            for b in batches
        ]
    }


@router.get("/ops/batch/{batch_id}")
def ops_chi_tiet_batch(
    batch_id: int,
    session: DbSession,
    user: Annotated[User, Depends(require("view_ops"))],
) -> dict:
    """Chi tiết lô + danh sách ảnh. KHÔNG trả ``uploader_id`` (quyền riêng tư)."""
    chi_tiet = batch_service.chi_tiet_batch(session, batch_id=batch_id)
    if chi_tiet is None:
        raise not_found("lô này")
    return chi_tiet
