"""Danh mục rác, lịch thu gom của toà, và kho quy định."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import delete, select

from src.api.deps import CurrentUser, DbSession, require
from src.api.errors import bad_request, not_found
from src.api.serializers import category_dict
from src.db.models import Building, CollectionSchedule, KnowledgeChunk, KnowledgeDoc, Unit, User, WasteCategory
from src.db.seed_data import KNOWN_LIMITATIONS, PICKUP_REJECT_REASONS
from src.models.schemas import (
    RetrievalTestRequest,
    UpdateCategoryRequest,
    UpdateScheduleRequest,
)
from src.services import rag
from src.services.auth import write_audit
from src.services.route_planner import STOP_ISSUES

router = APIRouter(tags=["catalog"])

WEEKDAY_LABELS_VI = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]


@router.get("/categories")
def list_categories(session: DbSession) -> dict:
    """Danh mục rác. UI đọc ``bin_color`` từ đây chứ không hardcode màu."""
    rows = session.scalars(select(WasteCategory).order_by(WasteCategory.sort_order)).all()
    return {"items": [category_dict(c) for c in rows]}


@router.patch("/categories/{code}")
def update_category(
    code: str,
    payload: UpdateCategoryRequest,
    session: DbSession,
    user: Annotated[User, Depends(require("edit_catalog"))],
) -> dict:
    """Sửa một nhóm rác.

    Hạ ``min_confidence`` của nhóm nguy hại là hành động rủi ro nên luôn ghi
    audit log, và API trả về cảnh báo để UI hiện hộp xác nhận.
    """
    category = session.scalar(select(WasteCategory).where(WasteCategory.code == code))
    if category is None:
        raise not_found(f"nhóm rác '{code}'")

    canh_bao = ""
    if payload.min_confidence is not None:
        if category.is_hazardous and payload.min_confidence < category.min_confidence:
            canh_bao = (
                "Hạ ngưỡng làm tăng rủi ro hướng dẫn sai cho nhóm rác nguy hại. "
                "Thay đổi này đã được ghi vào nhật ký kiểm toán."
            )
        category.min_confidence = payload.min_confidence
    for field in ("bin_color", "handling_note", "safety_warning"):
        value = getattr(payload, field)
        if value is not None:
            setattr(category, field, value)
    session.flush()

    write_audit(
        session,
        actor=user,
        action="update_category",
        entity="waste_category",
        entity_id=category.code,
        detail=payload.model_dump(exclude_none=True),
    )
    return {"category": category_dict(category), "warning_vi": canh_bao}


@router.get("/buildings")
def list_buildings(session: DbSession) -> dict:
    rows = session.scalars(select(Building).order_by(Building.code)).all()
    return {
        "items": [
            {"id": b.id, "code": b.code, "name": b.name, "address": b.address, "lat": b.lat, "lng": b.lng}
            for b in rows
        ]
    }


@router.get("/buildings/{building_id}/units")
def list_units(building_id: int, session: DbSession) -> dict:
    """Danh sách căn hộ của một toà — ô chọn căn hộ ở màn hồ sơ cư dân.

    Sắp theo mã căn hộ để danh sách trong ô chọn ổn định giữa các lần mở.
    """
    if session.get(Building, building_id) is None:
        raise not_found("toà nhà này")
    rows = session.scalars(select(Unit).where(Unit.building_id == building_id).order_by(Unit.code)).all()
    return {"items": [{"id": u.id, "code": u.code, "building_id": u.building_id} for u in rows]}


@router.get("/buildings/{building_id}/schedule")
def building_schedule(building_id: int, session: DbSession) -> dict:
    """Lịch thu gom của một toà. Frontend cache lại để xem được offline."""
    building = session.get(Building, building_id)
    if building is None:
        raise not_found("toà nhà này")

    rows = session.scalars(
        select(CollectionSchedule).where(CollectionSchedule.building_id == building_id)
    ).all()
    categories = {c.code: c for c in session.scalars(select(WasteCategory)).all()}

    return {
        "building": {"id": building.id, "code": building.code, "name": building.name},
        "items": [
            {
                "category_code": r.category_code,
                "category_name": categories[r.category_code].name if r.category_code in categories else r.category_code,
                "bin_color": categories[r.category_code].bin_color if r.category_code in categories else "",
                "icon": categories[r.category_code].icon if r.category_code in categories else "",
                "weekdays": r.weekdays,
                "weekdays_vi": [WEEKDAY_LABELS_VI[d] for d in r.weekdays if 0 <= d < 7],
                "window": r.window,
                "location": r.location,
            }
            for r in rows
        ],
    }


@router.put("/buildings/{building_id}/schedule")
def update_building_schedule(
    building_id: int,
    payload: UpdateScheduleRequest,
    session: DbSession,
    user: Annotated[User, Depends(require("manage_bins"))],
) -> dict:
    """Ghi đè lịch thu gom của một toà (thay toàn bộ hàng cũ).

    Quyền ``manage_bins`` — chỉ ban quản lý; collection schedule gắn liền với
    thùng/thu gom của toà. Validate: ``category_code`` phải tồn tại, ``weekdays``
    chỉ chứa 0..6 không trùng, ``window`` đúng dạng ``HH:MM-HH:MM`` hoặc rỗng.
    """
    import re

    building = session.get(Building, building_id)
    if building is None:
        raise not_found("toà nhà này")

    valid_codes = {c.code for c in session.scalars(select(WasteCategory)).all()}
    win_re = re.compile(r"^([01]\d|2[0-3]):[0-5]\d-([01]\d|2[0-3]):[0-5]\d$")
    for it in payload.items:
        if it.category_code not in valid_codes:
            raise bad_request(f"category_code không hợp lệ: {it.category_code}")
        seen: set[int] = set()
        for d in it.weekdays:
            if not isinstance(d, int) or isinstance(d, bool) or d < 0 or d > 6:
                raise bad_request(f"weekdays chỉ chứa số 0..6, gặp: {d!r}")
            if d in seen:
                raise bad_request(f"weekdays bị trùng ngày {d}")
            seen.add(d)
        if it.window and not win_re.match(it.window):
            raise bad_request(f"window phải có dạng HH:MM-HH:MM hoặc rỗng, gặp: {it.window!r}")

    # Thay toàn bộ: xoá hàng cũ của toà rồi thêm mới.
    session.execute(
        delete(CollectionSchedule).where(CollectionSchedule.building_id == building_id)
    )
    for it in payload.items:
        session.add(
            CollectionSchedule(
                building_id=building_id,
                category_code=it.category_code,
                weekdays=sorted(it.weekdays),
                window=it.window,
                location=it.location,
            )
        )
    session.flush()
    write_audit(
        session,
        actor=user,
        action="update_schedule",
        entity="collection_schedule",
        entity_id=str(building_id),
        detail={"items": [i.model_dump() for i in payload.items]},
    )
    return building_schedule(building_id, session)


@router.get("/knowledge")
def list_knowledge(
    session: DbSession,
    user: CurrentUser,
    building_id: int | None = None,
    doc_type: str = "",
) -> dict:
    """Danh sách tài liệu trong kho quy định."""
    statement = select(KnowledgeDoc)
    if building_id is not None:
        statement = statement.where(KnowledgeDoc.building_id == building_id)
    if doc_type:
        statement = statement.where(KnowledgeDoc.doc_type == doc_type)

    docs = session.scalars(statement.order_by(KnowledgeDoc.doc_type, KnowledgeDoc.title)).all()
    items = []
    for doc in docs:
        chunks = session.scalars(select(KnowledgeChunk).where(KnowledgeChunk.doc_id == doc.id)).all()
        items.append(
            {
                "id": doc.id,
                "title": doc.title,
                "doc_type": doc.doc_type,
                "source": doc.source,
                "building_id": doc.building_id,
                "effective_date": doc.effective_date.isoformat() if doc.effective_date else None,
                "chunk_count": len(chunks),
                "has_embedding": any(c.embedding for c in chunks),
                # Trích dẫn pháp luật là diễn giải rút gọn, phải đối chiếu văn
                # bản gốc trước khi đưa ra ngoài.
                "needs_verification": any((c.meta or {}).get("needs_verification") for c in chunks),
            }
        )
    return {"items": items}


@router.get("/knowledge/chunks/{chunk_id}")
def get_chunk(chunk_id: int, session: DbSession, user: CurrentUser) -> dict:
    """Nguyên văn một đoạn trích — bottom sheet khi bấm vào chip nguồn."""
    chunk = session.get(KnowledgeChunk, chunk_id)
    if chunk is None:
        raise not_found("đoạn quy định này")
    doc = session.get(KnowledgeDoc, chunk.doc_id)
    return {
        "id": chunk.id,
        "content": chunk.content,
        "section": chunk.section,
        "needs_verification": bool((chunk.meta or {}).get("needs_verification")),
        "doc": {
            "id": doc.id,
            "title": doc.title,
            "source": doc.source,
            "doc_type": doc.doc_type,
            "effective_date": doc.effective_date.isoformat() if doc and doc.effective_date else None,
        }
        if doc
        else None,
    }


@router.post("/knowledge/test-retrieval")
def test_retrieval(
    payload: RetrievalTestRequest,
    session: DbSession,
    user: Annotated[User, Depends(require("edit_catalog"))],
) -> dict:
    """Ô "Thử truy hồi" — gõ câu hỏi, xem hệ thống lấy ra đoạn nào và điểm bao nhiêu."""
    chunks = rag.retrieve(session, payload.query, building_id=payload.building_id, top_k=payload.top_k)
    return {
        "query": payload.query,
        "items": [
            {
                **c.as_source_dict(),
                "bm25_score": round(c.bm25_score, 4),
                "vector_score": round(c.vector_score, 4),
            }
            for c in chunks
        ],
        "note": "Điểm cuối là 0,65 × từ khoá + 0,35 × embedding khi có embedding; không có thì thuần từ khoá.",
    }


@router.get("/meta/enums")
def enums() -> dict:
    """Các danh sách cố định dùng chung giữa backend và frontend.

    Frontend đọc từ đây thay vì tự chép lại — chép lại là sớm muộn lệch nhau.
    """
    return {
        "pickup_reject_reasons": PICKUP_REJECT_REASONS,
        "stop_issues": STOP_ISSUES,
        "known_limitations": KNOWN_LIMITATIONS,
        "weekdays_vi": WEEKDAY_LABELS_VI,
    }
