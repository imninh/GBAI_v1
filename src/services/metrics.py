"""Tính số liệu vận hành và chất lượng AI từ dữ liệu thật trong CSDL.

Chương trình yêu cầu theo dõi tối thiểu **độ trễ, lỗi, chi phí** — ba khối
tương ứng ở đây. Không có con số nào được viết cứng: tất cả tính từ bảng
``classifications``, ``agent_runs`` và ``run_node_metrics``.

Bản ghi seed (``is_seed=True``) được **đếm riêng** và trả ra cờ ``has_seed_data``
để UI hiện nhãn "dữ liệu demo mô phỏng" — số mô phỏng và số đo thật không được
trộn vào nhau mà không nói gì.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.config import MODEL_PRICES_USD_PER_MTOK, get_settings
from src.db.models import AgentRun, Classification, EvalRun, FailureCase, RunNodeMetric, WasteCategory
from src.services.classifier import TIER_T0_CACHE, TIER_T05_LOCAL, TIER_T1, TIER_T2
from src.services.pickup_lifecycle import CHO_DUYET, trang_thai_tuong_duong

TIER_LABELS: dict[str, str] = {
    TIER_T0_CACHE: "T0 — cache pHash",
    TIER_T05_LOCAL: "T0.5 — model local (CLIP)",
    TIER_T1: "T1 — model vision rẻ",
    TIER_T2: "T2 — model vision mạnh",
    # Ca bị danh sách chặn cứng bắt trước khi gọi model, hoặc lỗi provider —
    # vẫn phải hiện ra để tổng tỉ lệ bằng 100%.
    "": "Chặn trước khi gọi model",
    "unknown": "Chặn trước khi gọi model",
}

# Các tầng chạy hoàn toàn trên máy chủ của mình nên **thật sự** tốn $0. Khác
# hẳn với "chưa tra được giá" — xem ``MODEL_PRICES_USD_PER_MTOK`` ở
# ``src/config.py``. Không phân biệt hai thứ này thì trang Vận hành hiện $0 cho
# tầng T1 và người đọc hiểu thành "T1 miễn phí".
TIER_MIEN_PHI_THAT: frozenset[str] = frozenset({TIER_T0_CACHE, TIER_T05_LOCAL, "", "unknown"})

# Nhãn cho các ca không chốt được nhóm rác (đã từ chối trả lời).
CHUA_XAC_DINH = "chua_xac_dinh"
CHUA_XAC_DINH_LABEL = "Chưa xác định (đã từ chối trả lời)"


def percentile(values: list[float], q: float) -> float:
    """Phân vị theo cách đơn giản (nearest-rank). Rỗng thì trả 0."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(q * len(ordered))) - 1))
    return float(ordered[index])


def cost_metrics(session: Session, *, since: datetime | None = None) -> dict[str, Any]:
    """Chi phí thật, chia theo tầng và theo ngày, kèm mốc so sánh.

    ``baseline_full_model`` là chi phí **giả định** nếu mọi ảnh đều chạy T2 —
    con số này chỉ có nghĩa khi giá của model T2 nằm trong bảng giá, nên có cờ
    ``baseline_price_known`` đi kèm.
    """
    settings = get_settings()
    statement = select(Classification)
    if since is not None:
        statement = statement.where(Classification.created_at >= since)
    rows = session.scalars(statement).all()

    by_tier: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"count": 0, "cost_usd": 0.0, "latency": [], "correct": 0, "verified": 0, "models": set()}
    )
    by_day: dict[str, float] = defaultdict(float)
    total_cost = 0.0

    for row in rows:
        bucket = by_tier[row.tier or "unknown"]
        bucket["count"] += 1
        bucket["cost_usd"] += row.cost_usd
        bucket["latency"].append(row.latency_ms)
        if row.model:
            bucket["models"].add(row.model)
        if row.human_label_id is not None:
            bucket["verified"] += 1
            if row.human_label_id == row.predicted_category_id:
                bucket["correct"] += 1
        total_cost += row.cost_usd
        by_day[row.created_at.date().isoformat()] += row.cost_usd

    total_count = len(rows) or 1
    _t1, model_t2, _text = settings.resolve_models()
    t2_rows = [r for r in rows if r.tier == TIER_T2]
    avg_t2_cost = (sum(r.cost_usd for r in t2_rows) / len(t2_rows)) if t2_rows else 0.0
    baseline = avg_t2_cost * len(rows)

    return {
        "total": round(total_cost, 6),
        "count": len(rows),
        "cost_per_1000": round(total_cost / total_count * 1000, 4),
        "by_tier": [
            {
                "tier": tier,
                "label_vi": TIER_LABELS.get(tier, tier),
                "share": round(data["count"] / total_count, 4),
                "count": data["count"],
                "cost_usd": round(data["cost_usd"], 6),
                "cost_per_item": round(data["cost_usd"] / data["count"], 6) if data["count"] else 0.0,
                # $0 vì chạy trên máy mình, hay $0 vì chưa tra được giá? UI phải
                # nói khác nhau cho hai ca này.
                "price_known": tier in TIER_MIEN_PHI_THAT
                or all(m in MODEL_PRICES_USD_PER_MTOK for m in data["models"]),
                "accuracy": round(data["correct"] / data["verified"], 4) if data["verified"] else None,
                "verified_count": data["verified"],
                "p95_latency_ms": int(percentile([float(v) for v in data["latency"]], 0.95)),
            }
            for tier, data in sorted(by_tier.items())
        ],
        "by_day": [{"date": day, "cost_usd": round(value, 6)} for day, value in sorted(by_day.items())],
        "baseline_full_model": round(baseline, 6),
        "baseline_model": model_t2,
        "baseline_price_known": model_t2 in MODEL_PRICES_USD_PER_MTOK,
        "saved_usd": round(max(0.0, baseline - total_cost), 6),
        "saved_ratio": round(1 - total_cost / baseline, 4) if baseline > 0 else 0.0,
        "budget": {"used": round(total_cost, 6), "limit": settings.budget_limit_usd},
    }


def latency_metrics(session: Session, *, since: datetime | None = None) -> dict[str, Any]:
    """Độ trễ p50/p95 theo node, và **thời gian người dùng thật sự cảm nhận**."""
    statement = select(RunNodeMetric)
    if since is not None:
        statement = statement.join(AgentRun).where(AgentRun.started_at >= since)
    nodes = session.scalars(statement).all()

    by_node: dict[str, list[float]] = defaultdict(list)
    for node in nodes:
        if node.status != "skipped":
            by_node[node.node].append(float(node.duration_ms))

    end_to_end = [float(c.latency_ms) for c in session.scalars(select(Classification)).all() if c.latency_ms]

    return {
        "by_node": [
            {
                "node": name,
                "p50": int(percentile(values, 0.5)),
                "p95": int(percentile(values, 0.95)),
                "count": len(values),
            }
            for name, values in sorted(by_node.items())
        ],
        # Chỉ số người dùng cảm nhận, quan trọng hơn độ trễ từng node.
        "end_to_end": {"p50": int(percentile(end_to_end, 0.5)), "p95": int(percentile(end_to_end, 0.95))},
    }


def error_metrics(session: Session, *, since: datetime | None = None) -> dict[str, Any]:
    """Tỉ lệ lỗi theo node và 10 lỗi gần nhất."""
    statement = select(RunNodeMetric)
    if since is not None:
        statement = statement.join(AgentRun).where(AgentRun.started_at >= since)
    nodes = session.scalars(statement).all()

    total = len(nodes) or 1
    errors = [n for n in nodes if n.status == "error"]
    by_node: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "errors": 0})
    for node in nodes:
        by_node[node.node]["total"] += 1
        if node.status == "error":
            by_node[node.node]["errors"] += 1

    recent = session.scalars(
        select(RunNodeMetric).where(RunNodeMetric.status == "error").order_by(RunNodeMetric.id.desc()).limit(10)
    ).all()

    return {
        "rate": round(len(errors) / total, 4),
        "by_node": [
            {
                "node": name,
                "rate": round(data["errors"] / data["total"], 4) if data["total"] else 0.0,
                "errors": data["errors"],
                "total": data["total"],
            }
            for name, data in sorted(by_node.items())
        ],
        "recent": [
            {"node": n.node, "error_type": n.error_type, "retries": n.retries, "run_id": n.run_id} for n in recent
        ],
        "rate_limit_hits": sum(1 for n in nodes if n.error_type.endswith("429")),
    }


def routing_metrics(session: Session) -> dict[str, Any]:
    """Tỉ lệ trúng cache và tỉ lệ leo tầng T2 — hai con số chứng minh kiến trúc."""
    rows = session.scalars(select(Classification)).all()
    total = len(rows) or 1
    cache_hits = sum(1 for r in rows if r.tier == TIER_T0_CACHE)
    local_hits = sum(1 for r in rows if r.tier == TIER_T05_LOCAL)
    escalated = sum(1 for r in rows if r.tier == TIER_T2)
    refused = sum(1 for r in rows if r.refused)
    return {
        "cache_hit_rate": round(cache_hits / total, 4),
        "local_model_rate": round(local_hits / total, 4),
        "escalation_rate": round(escalated / total, 4),
        "refusal_rate": round(refused / total, 4),
        "total_classifications": len(rows),
    }


def trend_metrics(session: Session, *, days: int) -> list[dict[str, Any]]:
    """Chuỗi thời gian cho biểu đồ xu hướng phân loại & thu gom.

    Trả đủ ``days`` ngày gần nhất tính theo **giờ VN (UTC+7)** — kể cả ngày
    không có dữ liệu (điểm = 0) để biểu đồ liền mạch. Không gọi model thật, chỉ
    đếm ``Classification.created_at`` (phân loại) và ``RouteStop.done_at`` (điểm
    thu gom hoàn thành) theo ngày VN.
    """
    from src.db.models import RouteStop

    mui_gio_vn = timedelta(hours=7)
    ngay_hom_nay = (datetime.now() + mui_gio_vn).date()
    # Danh sách ngày theo thứ tự cũ → mới.
    cac_ngay = [ngay_hom_nay - timedelta(days=i) for i in range(days - 1, -1, -1)]

    # Cửa sổ lùi an toàn: trừ thêm 1 ngày múi giờ để không sót ngày VN nào.
    tu_utc = datetime.now() - timedelta(days=days) - mui_gio_vn

    phan_loai_rows = session.scalars(
        select(Classification.created_at).where(Classification.created_at >= tu_utc)
    ).all()
    thu_gom_rows = session.scalars(
        select(RouteStop.done_at).where(RouteStop.done_at.is_not(None), RouteStop.done_at >= tu_utc)
    ).all()

    dem_phan_loai: dict[str, int] = defaultdict(int)
    for t in phan_loai_rows:
        if t is None:
            continue
        dem_phan_loai[(t + mui_gio_vn).date().isoformat()] += 1

    dem_thu_gom: dict[str, int] = defaultdict(int)
    for t in thu_gom_rows:
        if t is None:
            continue
        dem_thu_gom[(t + mui_gio_vn).date().isoformat()] += 1

    return [
        {
            "date": ng.isoformat(),
            "so_phan_loai": dem_phan_loai.get(ng.isoformat(), 0),
            "so_thu_gom": dem_thu_gom.get(ng.isoformat(), 0),
        }
        for ng in cac_ngay
    ]


def _trang_thai_truy_hoi(session: Session) -> dict[str, Any]:
    """Truy hồi đang chạy hybrid hay thuần từ khoá — và bằng chứng cho câu trả lời.

    Trước 02/08/2026 phần embedding có code nhưng chưa từng được nối, nên tài
    liệu ghi "hybrid" mà thực tế là BM25. Đưa hẳn lên trang Vận hành để lần sau
    không ai phải đoán.
    """
    from src.services.rag import so_doan_co_embedding

    settings = get_settings()
    co, tong = so_doan_co_embedding(session)
    return {
        "che_do": "hybrid" if co else "bm25",
        "chunks_co_embedding": co,
        "chunks_tong": tong,
        "embedding_provider": settings.resolve_embedding_provider(),
        "embedding_model": settings.resolve_embedding_model(),
        "vector_weight": settings.rag_vector_weight,
    }


def ops_metrics(session: Session, *, days: int = 30) -> dict[str, Any]:
    """Gói toàn bộ số liệu cho trang Vận hành."""
    from src.db.seed_data import KNOWN_LIMITATIONS
    from src.services import luu_tru
    from src.services.vision import local_model_loaded, provider_status, yolo_loaded

    since = datetime.now() - timedelta(days=days)
    seed_count = session.scalar(select(func.count(Classification.id)).where(Classification.is_seed.is_(True))) or 0

    return {
        "cost": cost_metrics(session, since=since),
        "latency": latency_metrics(session, since=since),
        "errors": error_metrics(session, since=since),
        "routing": routing_metrics(session),
        # Cố tình dùng bản không có tác dụng phụ: endpoint chỉ đọc không được
        # kích hoạt việc tải model 350MB.
        "provider": {
            **provider_status(),
            "local_model_loaded": local_model_loaded(),
            "yolo_enabled": get_settings().yolo_enabled,
            "yolo_loaded": yolo_loaded(),
        },
        "storage": luu_tru.kiem_tra(),
        "retrieval": _trang_thai_truy_hoi(session),
        "known_limitations": KNOWN_LIMITATIONS,
        "has_seed_data": seed_count > 0,
        "seed_count": seed_count,
        "seed_note": (
            "Một phần số liệu trên trang này đến từ dữ liệu demo mô phỏng, "
            "được đánh dấu riêng trong cơ sở dữ liệu."
        )
        if seed_count
        else "",
    }


def eval_summary(session: Session) -> dict[str, Any]:
    """Số liệu cho trang Chất lượng AI.

    Chỉ số an toàn cốt lõi — **rác nguy hại bị phân loại thành rác thường** —
    tính trực tiếp từ các ca đã có người xác nhận, không lấy từ bảng eval, để
    nó luôn phản ánh dữ liệu mới nhất.
    """
    verified = session.scalars(select(Classification).where(Classification.human_label_id.is_not(None))).all()
    categories = {c.id: c for c in session.scalars(select(WasteCategory)).all()}

    dung = sum(1 for c in verified if c.human_label_id == c.predicted_category_id)
    hazard_true = [c for c in verified if categories.get(c.human_label_id) and categories[c.human_label_id].is_hazardous]
    hazard_missed = [
        c
        for c in hazard_true
        if not (categories.get(c.predicted_category_id) and categories[c.predicted_category_id].is_hazardous)
    ]

    ma_tran: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for c in verified:
        thuc = categories.get(c.human_label_id)
        doan = categories.get(c.predicted_category_id)
        ma_tran[thuc.code if thuc else "?"][doan.code if doan else "tu_choi"] += 1

    runs = session.scalars(select(EvalRun).order_by(EvalRun.created_at.desc())).all()
    failures = session.scalars(select(FailureCase).order_by(FailureCase.created_at.desc()).limit(50)).all()

    return {
        "safety": {
            "hazard_missed_count": len(hazard_missed),
            "hazard_total": len(hazard_true),
            "target": 0,
            "label_vi": "Rác nguy hại bị phân loại thành rác thường",
        },
        "accuracy": round(dung / len(verified), 4) if verified else None,
        "verified_count": len(verified),
        "hazard_recall": round(1 - len(hazard_missed) / len(hazard_true), 4) if hazard_true else None,
        "confusion_matrix": {k: dict(v) for k, v in ma_tran.items()},
        "by_dataset": [
            {
                "dataset": r.dataset,
                "test_size": r.test_size,
                "accuracy": r.accuracy,
                "macro_f1": r.macro_f1,
                "hazard_recall": r.hazard_recall,
                "hazard_missed_count": r.hazard_missed_count,
                "retrieval_precision_at_5": r.retrieval_precision_at_5,
                "prompt_version": r.prompt_version,
                "model": r.model,
                "avg_cost_usd": r.avg_cost_usd,
                "p95_latency_ms": r.p95_latency_ms,
                "is_seed": r.is_seed,
                "created_at": r.created_at.isoformat(),
            }
            for r in runs
        ],
        "failures": [
            {
                "id": f.id,
                "media_id": f.media_id,
                "item_name": f.item_name,
                "true_category_code": f.true_category_code,
                "predicted_category_code": f.predicted_category_code,
                "confidence": f.confidence,
                "cause": f.cause,
                "resolved": f.resolved,
                "is_seed": f.is_seed,
            }
            for f in failures
        ],
        "has_seed_data": any(r.is_seed for r in runs) or any(f.is_seed for f in failures),
    }


def manager_overview(session: Session, *, building_id: int | None = None) -> dict[str, Any]:
    """Số liệu cho màn Tổng quan của BQL — trả lời "hôm nay có gì cần tôi xử lý"."""
    from src.db.models import Alert, PickupRequest, PickupRoute

    cho_duyet_thu_gom = session.scalar(
        select(func.count(PickupRequest.id)).where(PickupRequest.status.in_(trang_thai_tuong_duong(CHO_DUYET)))
    ) or 0
    cho_xac_nhan_nhan = session.scalar(
        select(func.count(Classification.id)).where(
            Classification.escalated_to_human.is_(True), Classification.human_label_id.is_(None)
        )
    ) or 0
    cho_duyet_tuyen = session.scalar(
        select(func.count(PickupRoute.id)).where(PickupRoute.status == "proposed")
    ) or 0

    tuan_truoc = datetime.now() - timedelta(days=7)
    tuan_nay_rows = session.scalars(
        select(Classification).where(Classification.created_at >= tuan_truoc)
    ).all()
    tuan_truoc_rows = session.scalars(
        select(Classification).where(
            Classification.created_at >= tuan_truoc - timedelta(days=7),
            Classification.created_at < tuan_truoc,
        )
    ).all()

    categories = {c.id: c for c in session.scalars(select(WasteCategory)).all()}
    phan_bo: dict[str, int] = defaultdict(int)
    for row in tuan_nay_rows:
        category = categories.get(row.predicted_category_id)
        phan_bo[category.code if category else CHUA_XAC_DINH] += 1

    eval_data = eval_summary(session)

    routes = session.scalars(select(PickupRoute).where(PickupRoute.status.in_(["approved", "done"]))).all()
    tong_yeu_cau = sum(len(r.stops) for r in routes)
    tiet_kiem_km = sum((r.reasoning or {}).get("saved_km", 0) for r in routes)

    alerts = session.scalars(
        select(Alert).where(Alert.ack.is_(False)).order_by(Alert.triggered_at.desc()).limit(5)
    ).all()

    return {
        "queues": {
            "pickup": cho_duyet_thu_gom,
            "labels": cho_xac_nhan_nhan,
            "routes": cho_duyet_tuyen,
            "total": cho_duyet_thu_gom + cho_xac_nhan_nhan + cho_duyet_tuyen,
        },
        "classifications_this_week": len(tuan_nay_rows),
        "classifications_last_week": len(tuan_truoc_rows),
        "growth": round((len(tuan_nay_rows) - len(tuan_truoc_rows)) / len(tuan_truoc_rows), 4)
        if tuan_truoc_rows
        else None,
        "accuracy": eval_data["accuracy"],
        "verified_count": eval_data["verified_count"],
        "safety": eval_data["safety"],
        "category_distribution": [
            {
                "code": code,
                "name": next(
                    (c.name for c in categories.values() if c.code == code),
                    CHUA_XAC_DINH_LABEL if code == CHUA_XAC_DINH else code,
                ),
                "bin_color": next((c.bin_color for c in categories.values() if c.code == code), ""),
                "count": count,
                "share": round(count / len(tuan_nay_rows), 4) if tuan_nay_rows else 0.0,
            }
            for code, count in sorted(phan_bo.items(), key=lambda kv: -kv[1])
        ],
        "routing_efficiency": {
            "so_yeu_cau": tong_yeu_cau,
            "so_chuyen": len(routes),
            "giam_so_chuyen": max(0, tong_yeu_cau - len(routes)),
            "tiet_kiem_km": round(tiet_kiem_km, 1),
        },
        "alerts": [
            {
                "id": a.id,
                "severity": a.severity,
                "title": a.title,
                "threshold": a.threshold,
                "triggered_at": a.triggered_at.isoformat(),
                "ack": a.ack,
            }
            for a in alerts
        ],
    }
