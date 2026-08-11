"""Phân loại rác — màn chính của cư dân và của đội vệ sinh tại phòng rác.

Toàn bộ luồng đi qua graph agent, và **mọi ảnh đều qua tiền xử lý trước khi rời
máy chủ**: tước EXIF, làm mờ khuôn mặt, nén 512px. Không có đường tắt nào bỏ
qua bước đó.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from src.agents.graph import agent
from src.api.deps import CurrentUser, DbSession, require
from src.api.errors import bad_request, not_found
from src.api.serializers import classification_dict
from src.db.models import (
    Classification,
    ClassificationFeedback,
    Media,
    User,
    WasteCategory,
)
from src.models.schemas import ClassifyTextRequest, FeedbackRequest, VerifyRequest
from src.services import runs
from src.services.auth import write_audit
from src.services.image import preprocess_image
from src.services.safety import HARD_BLOCK_RULES

router = APIRouter(tags=["classify"])

MAX_IMAGE_BYTES = 12 * 1024 * 1024


def _run_pipeline(
    session: Session,
    *,
    user: User,
    image_bytes: bytes | None,
    media: Media | None,
    text_query: str,
    building_id: int | None,
) -> dict[str, Any]:
    """Chạy graph agent rồi ghi bản ghi phân loại + số liệu run."""
    run = runs.start_run(session, kind="classify", trigger="user")

    state = agent.invoke(
        {
            "session": session,
            "image_bytes": image_bytes,
            "image_phash": media.phash if media else "",
            "text_query": text_query,
            "building_id": building_id,
            "user_id": user.id,
        }
    )

    outcome = state["outcome"]
    advice = state.get("advice")
    nodes = state.get("nodes", [])

    category = outcome.category
    classification = Classification(
        media_id=media.id if media else None,
        text_query=text_query,
        input_type="image" if media else "text",
        asker_id=user.id,
        building_id=building_id,
        item_name=outcome.item_name or outcome.guess_item_name,
        items=outcome.items,
        predicted_category_id=category.id if category else None,
        confidence=outcome.confidence,
        tier=outcome.tier,
        model=outcome.model,
        prompt_version=outcome.prompt_version,
        refused=outcome.refused,
        refusal_reason=outcome.refusal_reason,
        escalated_to_human=outcome.refused,
        escalation_reason=outcome.escalation_reason,
        advice=advice.advice if advice else "",
        advice_sources=[s.as_source_dict() for s in advice.sources] if advice else [],
        degraded=bool(advice and advice.degraded),
        degraded_note=advice.degraded_note if advice else "",
        latency_ms=outcome.latency_ms,
        cost_usd=outcome.cost_usd,
        run_id=run.id,
    )
    session.add(classification)
    session.flush()

    runs.finish_run(session, run, nodes=nodes)

    data = classification_dict(session, classification, full=True)
    # Phần chỉ có ở lần trả về ngay sau khi phân loại, không lưu vào bảng.
    data["refusal_headline_vi"] = outcome.refusal_headline_vi
    data["guess"] = (
        {"item_name": outcome.guess_item_name, "category_code": outcome.guess_category_code}
        if outcome.refused
        else None
    )
    data["hard_block"] = (
        {
            "code": outcome.hard_block.code,
            "label_vi": outcome.hard_block.label_vi,
            "instruction_vi": outcome.hard_block.instruction_vi,
        }
        if outcome.hard_block
        else None
    )
    data["schedule_hint"] = state.get("schedule_hint", {})
    data["price_known"] = outcome.price_known
    return data


@router.post("/classify")
async def classify(
    session: DbSession,
    user: CurrentUser,
    image: Annotated[UploadFile | None, File()] = None,
    text_query: Annotated[str, Form()] = "",
    building_id: Annotated[int | None, Form()] = None,
) -> dict:
    """Phân loại một món rác từ ảnh hoặc từ mô tả bằng chữ.

    Nhận ``multipart/form-data``. Ảnh được tiền xử lý ngay khi tới, trước khi
    bất kỳ lệnh gọi model nào xảy ra.
    """
    if image is None and not text_query.strip():
        raise bad_request("Gửi kèm ảnh hoặc mô tả bằng chữ giúp mình nhé.", code="REQ-400")

    media: Media | None = None
    image_bytes: bytes | None = None

    if image is not None:
        raw = await image.read()
        if not raw:
            raise bad_request("File ảnh rỗng.", code="IMG-400")
        if len(raw) > MAX_IMAGE_BYTES:
            raise bad_request("Ảnh quá lớn, tối đa 12 MB.", code="IMG-413")

        try:
            processed = preprocess_image(raw)
        except ValueError as exc:
            raise bad_request("Mình không đọc được file ảnh này.", code="IMG-415") from exc

        media = Media(
            uploader_id=user.id,
            stored_path=processed.stored_path,
            original_path=processed.original_path,
            phash=processed.phash,
            width=processed.width,
            height=processed.height,
            bytes_size=processed.bytes_size,
            original_width=processed.original_width,
            original_height=processed.original_height,
            original_bytes_size=processed.original_bytes_size,
            exif_stripped=processed.exif_stripped,
            faces_blurred=processed.faces_blurred,
            removed_fields=processed.removed_fields_as_json(),
            expires_at=processed.expires_at,
        )
        session.add(media)
        session.flush()
        with open(processed.stored_path, "rb") as handle:
            image_bytes = handle.read()

    building = building_id
    if building is None and user.unit_id:
        from src.db.models import Unit

        unit = session.get(Unit, user.unit_id)
        building = unit.building_id if unit else None

    return _run_pipeline(
        session,
        user=user,
        image_bytes=image_bytes,
        media=media,
        text_query=text_query.strip(),
        building_id=building,
    )


@router.post("/classify/text")
def classify_text(payload: ClassifyTextRequest, session: DbSession, user: CurrentUser) -> dict:
    """Phân loại theo mô tả bằng chữ — dùng cho các chip gợi ý nhanh khi demo."""
    building = payload.building_id
    if building is None and user.unit_id:
        from src.db.models import Unit

        unit = session.get(Unit, user.unit_id)
        building = unit.building_id if unit else None

    return _run_pipeline(
        session,
        user=user,
        image_bytes=None,
        media=None,
        text_query=payload.text_query.strip(),
        building_id=building,
    )


@router.get("/classifications")
def list_classifications(
    session: DbSession,
    user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    refused_only: bool = False,
    verified_only: bool = False,
    wrong_only: bool = False,
    tier: str = "",
    category_code: str = "",
    building_id: int | None = None,
) -> dict:
    """Lịch sử phân loại. Cư dân chỉ thấy của mình, BQL thấy tất cả."""
    statement = select(Classification)
    if user.role == "resident":
        statement = statement.where(Classification.asker_id == user.id)
    if refused_only:
        statement = statement.where(Classification.refused.is_(True))
    if verified_only:
        statement = statement.where(Classification.human_label_id.is_not(None))
    if wrong_only:
        statement = statement.where(
            Classification.human_label_id.is_not(None),
            Classification.human_label_id != Classification.predicted_category_id,
        )
    if tier:
        statement = statement.where(Classification.tier == tier)
    if building_id is not None:
        statement = statement.where(Classification.building_id == building_id)
    if category_code:
        category = session.scalar(select(WasteCategory).where(WasteCategory.code == category_code))
        statement = statement.where(Classification.predicted_category_id == (category.id if category else -1))

    total = len(session.scalars(statement).all())
    rows = session.scalars(
        statement.order_by(desc(Classification.created_at)).offset((page - 1) * page_size).limit(page_size)
    ).all()

    return {
        "items": [classification_dict(session, c) for c in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/classifications/{classification_id}")
def get_classification(classification_id: int, session: DbSession, user: CurrentUser) -> dict:
    classification = session.get(Classification, classification_id)
    if classification is None:
        raise not_found("lần phân loại này")
    if user.role == "resident" and classification.asker_id != user.id:
        raise not_found("lần phân loại này")
    return classification_dict(session, classification, full=True)


@router.post("/classifications/{classification_id}/feedback")
def send_feedback(
    classification_id: int,
    payload: FeedbackRequest,
    session: DbSession,
    user: CurrentUser,
) -> dict:
    """Nút 👍 Hữu ích / 👎 Sai rồi.

    Bấm 👎 đẩy ca đó vào hàng đợi xác nhận nhãn của BQL — dữ liệu này chảy
    ngược vào tập cải tiến (PLO 7).
    """
    classification = session.get(Classification, classification_id)
    if classification is None:
        raise not_found("lần phân loại này")

    session.add(
        ClassificationFeedback(
            classification_id=classification.id,
            user_id=user.id,
            is_correct=payload.is_correct,
            suggested_category_code=payload.suggested_category_code,
        )
    )
    if not payload.is_correct:
        classification.escalated_to_human = True
    session.flush()
    return {"ok": True, "escalated_to_human": classification.escalated_to_human}


@router.get("/verify-queue")
def verify_queue(
    session: DbSession,
    user: Annotated[User, Depends(require("verify_label"))],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    """Hàng đợi xác nhận nhãn — HITL #2.

    Gồm các ca hệ thống **đã từ chối trả lời** và các ca cư dân bấm 👎.
    """
    statement = (
        select(Classification)
        .where(Classification.escalated_to_human.is_(True), Classification.human_label_id.is_(None))
        .order_by(desc(Classification.created_at))
    )
    total = len(session.scalars(statement).all())
    rows = session.scalars(statement.offset((page - 1) * page_size).limit(page_size)).all()

    from src.db.seed_data import HARD_CASES

    return {
        "items": [classification_dict(session, c, full=True) for c in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        # Khối "Ca khó" ghim trên cùng — người duyệt biết trước chỗ dễ sai thì
        # duyệt chính xác hơn (spec 4.11).
        "hard_cases": HARD_CASES,
    }


@router.post("/classifications/{classification_id}/verify")
def verify_label(
    classification_id: int,
    payload: VerifyRequest,
    session: DbSession,
    user: Annotated[User, Depends(require("verify_label"))],
) -> dict:
    """HITL #2 — người xác nhận nhãn đúng cho một ca nghi ngờ."""
    classification = session.get(Classification, classification_id)
    if classification is None:
        raise not_found("lần phân loại này")

    category = session.scalar(select(WasteCategory).where(WasteCategory.code == payload.category_code))
    if category is None:
        raise bad_request(f"Không có nhóm rác mã '{payload.category_code}'.", code="CAT-404")

    from datetime import datetime

    classification.human_label_id = category.id
    classification.verified_by = user.id
    classification.verified_at = datetime.now()
    if payload.reply_text:
        classification.advice = payload.reply_text
    session.flush()

    write_audit(
        session,
        actor=user,
        action="verify_label",
        entity="classification",
        entity_id=str(classification.id),
        detail={"category_code": category.code},
    )
    return classification_dict(session, classification, full=True)


@router.get("/safety/hard-blocks")
def hard_blocks() -> dict:
    """Danh sách chặn cứng — công khai để UI hiện được màn "danh mục nguy hại"."""
    return {
        "rules": [
            {"code": r.code, "label_vi": r.label_vi, "instruction_vi": r.instruction_vi}
            for r in HARD_BLOCK_RULES
        ]
    }
