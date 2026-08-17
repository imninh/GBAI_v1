"""Ghi lại mỗi lần chạy agent — nguồn dữ liệu cho màn Agent Run và trang Vận hành.

Chương trình yêu cầu theo dõi tối thiểu **độ trễ, lỗi, chi phí**, và yêu cầu
workflow agentic phải **trace và debug được**. Hai yêu cầu đó gặp nhau ở đây:
mỗi node đi qua đều để lại một bản ghi ``RunNodeMetric``, không có ngoại lệ.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from src.db.models import AgentRun, RunNodeMetric
from src.services.classifier import NodeMetric

logger = logging.getLogger(__name__)


def _ve_kieu_python(gia_tri: object) -> object:
    """Đổi mọi kiểu vô danh (numpy scalar…) về kiểu Python ghi JSON được.

    Cột `meta` là JSON. Thư viện numpy trả `int64`/`float32` tuỳ **phiên bản**:
    numpy 2.x cho `int`, numpy 1.x cho `int64` — cùng một dòng mã, máy dev chạy
    tốt còn máy chủ nổ `TypeError: Object of type int64 is not JSON serializable`
    (sự cố 16/08/2026, mất trắng cả một lần phân loại vì một con số thống kê).
    Chặn ở đây thay vì đuổi theo từng field.
    """
    if isinstance(gia_tri, dict):
        return {k: _ve_kieu_python(v) for k, v in gia_tri.items()}
    if isinstance(gia_tri, (list, tuple)):
        return [_ve_kieu_python(v) for v in gia_tri]
    # numpy scalar có `.item()` trả về giá trị Python tương đương. Nhận diện bằng
    # hasattr thay vì import numpy — máy chạy có thể không cài numpy.
    if hasattr(gia_tri, "item"):
        try:
            return _ve_kieu_python(gia_tri.item())
        except (TypeError, ValueError, OverflowError):
            return str(gia_tri)
    if gia_tri is None or isinstance(gia_tri, (bool, int, float, str)):
        return gia_tri
    return str(gia_tri)


def _khoa_bi_doi(gia_tri: object, tien_to: str = "") -> list[tuple[str, str]]:
    """Liệt kê chỗ nào trong ``meta`` sẽ phải đổi kiểu trước khi ghi.

    Returns:
        ``[(đường_dẫn, tên_kiểu_gốc), …]``. Đường dẫn như ``"so_vat"`` hay
        ``"ds[0][\"a\"]"`` để người đọc log tìm ra ngay thủ phạm sinh numpy.
    """
    if isinstance(gia_tri, dict):
        cac_cho: list[tuple[str, str]] = []
        for khoa, con in gia_tri.items():
            duong = f"{tien_to}.{khoa}" if tien_to else str(khoa)
            cac_cho.extend(_khoa_bi_doi(con, duong))
        return cac_cho
    if isinstance(gia_tri, (list, tuple)):
        cac_cho = []
        for chi_so, con in enumerate(gia_tri):
            cac_cho.extend(_khoa_bi_doi(con, f"{tien_to}[{chi_so}]"))
        return cac_cho
    if gia_tri is not None and not isinstance(gia_tri, (bool, int, float, str)) and hasattr(gia_tri, "item"):
        return [(tien_to, type(gia_tri).__name__)]
    return []


def start_run(session: Session, *, kind: str = "classify", trigger: str = "user") -> AgentRun:
    """Mở một lần chạy ở trạng thái ``running``."""
    run = AgentRun(kind=kind, trigger=trigger, status="running")
    session.add(run)
    session.flush()
    return run


def record_nodes(session: Session, run: AgentRun, nodes: list[NodeMetric]) -> None:
    """Ghi số liệu từng node vào CSDL."""
    for node in nodes:
        meta = _ve_kieu_python(node.meta or {})
        for duong, loai in _khoa_bi_doi(node.meta or {}):
            logger.warning(
                "meta node %s chứa kiểu %s tại '%s' — đã đổi về kiểu Python trước khi ghi",
                node.node,
                loai,
                duong,
            )
        session.add(
            RunNodeMetric(
                run_id=run.id,
                node=node.node,
                status=node.status,
                duration_ms=node.duration_ms,
                tokens_in=node.tokens_in,
                tokens_out=node.tokens_out,
                image_tokens=node.image_tokens,
                cost_usd=node.cost_usd,
                cache_hits=node.cache_hits,
                llm_calls=node.llm_calls,
                retries=node.retries,
                error_type=node.error_type,
                meta=meta,
            )
        )
    session.flush()


def finish_run(
    session: Session,
    run: AgentRun,
    *,
    nodes: list[NodeMetric],
    items_processed: int = 1,
    error: str = "",
) -> AgentRun:
    """Đóng một lần chạy: ghi node, cộng chi phí, tính tổng thời gian."""
    record_nodes(session, run, nodes)
    run.items_processed = items_processed
    run.total_cost_usd = round(sum(n.cost_usd for n in nodes), 6)
    run.duration_ms = sum(n.duration_ms for n in nodes)
    run.finished_at = datetime.now()
    run.error = error
    # Một node lỗi mà pipeline vẫn ra kết quả thì đó là "suy giảm một phần",
    # không phải hỏng — trạng thái riêng để trang Vận hành đếm đúng.
    has_error = any(n.status == "error" for n in nodes)
    run.status = "error" if error else ("degraded" if has_error else "ok")
    session.flush()
    return run


def run_to_dict(run: AgentRun, nodes: list[RunNodeMetric]) -> dict[str, Any]:
    """Khuôn dữ liệu cho ``GET /api/v1/runs/{id}``."""
    return {
        "id": run.id,
        "kind": run.kind,
        "trigger": run.trigger,
        "status": run.status,
        "items_processed": run.items_processed,
        "duration_ms": run.duration_ms,
        "total_cost_usd": run.total_cost_usd,
        "started_at": run.started_at.isoformat() if run.started_at else "",
        "finished_at": run.finished_at.isoformat() if run.finished_at else "",
        "error": run.error,
        "is_seed": run.is_seed,
        "nodes": [
            {
                "node": n.node,
                "status": n.status,
                "duration_ms": n.duration_ms,
                "tokens_in": n.tokens_in,
                "tokens_out": n.tokens_out,
                "image_tokens": n.image_tokens,
                "cost_usd": n.cost_usd,
                "cache_hits": n.cache_hits,
                "llm_calls": n.llm_calls,
                "retries": n.retries,
                "error_type": n.error_type,
                "meta": n.meta,
            }
            for n in nodes
        ],
    }
