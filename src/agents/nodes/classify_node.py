"""Ba node của pipeline GreenBin: phân loại → tra quy định → gợi ý lịch thu gom.

Mỗi node đều tự bồi số liệu vào ``state["nodes"]`` — không có node nào chạy
"âm thầm". Đó là điều kiện để màn Agent Run dựng lại được toàn bộ hành trình.
"""

from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select

from src.agents.state import GreenBinState
from src.db.models import CollectionSchedule, PickupRoute
from src.services import rag
from src.services.classifier import NodeMetric, classify_waste


def classify_node(state: GreenBinState) -> dict[str, Any]:
    """Nhận diện món rác qua định tuyến 4 tầng."""
    session = state["session"]
    outcome = classify_waste(
        session,
        image_bytes=state.get("image_bytes"),
        image_phash=state.get("image_phash", ""),
        text_query=state.get("text_query", ""),
    )
    return {"outcome": outcome, "nodes": list(outcome.nodes)}


def advise_node(state: GreenBinState) -> dict[str, Any]:
    """Tra quy định của toà và viết hướng dẫn có trích nguồn."""
    session = state["session"]
    outcome = state["outcome"]
    started = time.perf_counter()

    result = rag.advise(
        session,
        item_name=outcome.item_name,
        category=outcome.category,
        building_id=state.get("building_id"),
        query=state.get("text_query", ""),
    )

    metric = NodeMetric(
        node="advise",
        status="degraded" if result.degraded else "ok",
        duration_ms=int((time.perf_counter() - started) * 1000),
        tokens_in=result.usage.tokens_in,
        tokens_out=result.usage.tokens_out,
        cost_usd=result.usage.cost_usd,
        llm_calls=1 if result.generated_by == "llm" else 0,
        meta={
            "so_chunk_truy_hoi": len(result.sources),
            "loc_theo_building_id": state.get("building_id"),
            "sinh_boi": result.generated_by,
        },
    )
    return {"advice": result, "nodes": [*state.get("nodes", []), metric]}


def skip_advise_node(state: GreenBinState) -> dict[str, Any]:
    """Nhánh bỏ qua khi hệ thống đã từ chối trả lời.

    Từ chối rồi mà vẫn đi tra quy định là vừa tốn tiền vừa sai thông điệp: màn
    "Mình chưa chắc" không được kèm hướng dẫn xử lý.
    """
    metric = NodeMetric(node="advise", status="skipped", meta={"ly_do": "he_thong_tu_choi_tra_loi"})
    return {"nodes": [*state.get("nodes", []), metric]}


def schedule_node(state: GreenBinState) -> dict[str, Any]:
    """Gợi ý khung giờ thu gom, ưu tiên khung đã có chuyến của toà.

    Đây là chỗ **giá trị kinh doanh của agent hiện ra ngay trước mắt người
    dùng**: chọn khung đã có chuyến thì tiết kiệm được một chuyến xe.
    """
    session = state["session"]
    outcome = state["outcome"]
    started = time.perf_counter()
    building_id = state.get("building_id")

    lich = []
    if building_id is not None and outcome.category is not None:
        codes = [outcome.category.code]
        if outcome.category.parent_code:
            codes.append(outcome.category.parent_code)
        rows = session.scalars(
            select(CollectionSchedule).where(
                CollectionSchedule.building_id == building_id,
                CollectionSchedule.category_code.in_(codes),
            )
        ).all()
        lich = [
            {"weekdays": r.weekdays, "window": r.window, "location": r.location, "category_code": r.category_code}
            for r in rows
        ]

    # Các chuyến đã có trong 7 ngày tới — chọn trùng khung là gộp được.
    hom_nay = date.today()
    chuyen_da_co = session.scalars(
        select(PickupRoute).where(
            PickupRoute.service_date >= hom_nay,
            PickupRoute.service_date <= hom_nay + timedelta(days=7),
            PickupRoute.status.in_(["proposed", "approved"]),
        )
    ).all()

    hint = {
        "la_do_cong_kenh": bool(outcome.category and outcome.category.code == "bulky"),
        "lich_thu_gom": lich,
        "khung_gio_da_co_chuyen": [
            {
                "service_date": r.service_date.isoformat(),
                "window": r.window,
                "so_diem_dung": len(r.stops),
                "ghi_chu": "Đã có chuyến của toà — chọn khung này giúp tiết kiệm 1 chuyến xe",
            }
            for r in chuyen_da_co
        ],
    }

    metric = NodeMetric(
        node="schedule_pickup",
        duration_ms=int((time.perf_counter() - started) * 1000),
        meta={"so_khung_gio_goi_y": len(hint["khung_gio_da_co_chuyen"]), "so_lich_thu_gom": len(lich)},
    )
    return {"schedule_hint": hint, "nodes": [*state.get("nodes", []), metric]}


def skip_schedule_node(state: GreenBinState) -> dict[str, Any]:
    """Bỏ qua khi món rác không phải đồ cồng kềnh."""
    metric = NodeMetric(node="schedule_pickup", status="skipped", meta={"ly_do": "khong_phai_do_cong_kenh"})
    return {"schedule_hint": {}, "nodes": [*state.get("nodes", []), metric]}
