"""IoT device API — image captures and bin fill readings.

Thin by design (spec §9): this module handles HTTP concerns only — auth,
parsing, status codes. Every decision lives in ``src.services``.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.deps import DbSession
from src.config import get_settings
from src.db.models import Bin, Classification, Media, WasteCategory
from src.models.schemas import (
    HeartbeatRequest,
    HeartbeatResponse,
)
from src.services import bin_readings, phien_thung, runs
from src.services.classifier import classify_waste
from src.services.classifier_types import ClassifyOutcome
from src.services.device_auth import DeviceAuthError, authenticate
from src.services.hop_dong_thiet_bi import dung_phan_hoi, sinh_item_id
from src.services.image_privacy import ImageValidationError, preprocess_image
from src.services.kieu_json import lam_sach_gia_tri
from src.services.luu_tru import tai_len

router = APIRouter()

logger = logging.getLogger(__name__)


async def require_device_key(x_device_key: str | None = Header(default=None)) -> str:
    """FastAPI dependency: authenticate the caller as a known device."""
    try:
        return authenticate(x_device_key)
    except DeviceAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/iot/captures")
async def create_capture(
    session: DbSession,
    image: UploadFile = File(...),
    device_id: str = Form(...),
    bin_code: str = Form(...),
    event_type: str = Form(default="waste_detected"),
    uptime_s: int = Form(default=0),
    fill_percent: float | None = Form(default=None),
    item_id: str = Form(default=""),
    authenticated_device: str = Depends(require_device_key),
) -> dict:
    """Accept a JPEG from a device, preprocess it, classify it, return the result.

    Gói P61/P58 thay ruột: endpoint đi qua **bộ phân loại 4 tầng**
    (:func:`src.services.classifier.classify_waste`) như mọi nguồn ảnh khác,
    ghi ``Media`` (``uploader_id=None`` — thiết bị không có tài khoản) và
    ``Classification`` xuống CSDL, rồi dựng phản hồi thiết bị CP2
    (:func:`src.services.hop_dong_thiet_bi.dung_phan_hoi`) — giữ nguyên mọi
    trường hợp đồng cũ và thêm ``route`` / ``item_id`` / ``review_required`` /
    ``model_version``.

    Gói P63: sau khi phân loại, tự tra phiên bỏ rác đang mở của thùng (qua
    ``bin_code``) và gắn kết quả vào — **thiết bị không cần biết "phiên" là gì**,
    firmware không phải sửa một dòng. Không có phiên thì vẫn phân loại bình
    thường, chỉ là không ai được điểm. Phần phiên hỏng không được làm hỏng phản
    hồi phân loại.
    """
    # A valid key for device A may not post as device B.
    if device_id != authenticated_device:
        raise HTTPException(status_code=401, detail="Invalid device credentials")

    ma_item = sinh_item_id(item_id)

    # Idempotency (CP2): cùng `item_id` gửi lại → trả kết quả cũ, không tạo bản
    # ghi thứ hai. `item_id` nằm ở cột RIÊNG (`Classification.item_id`), không
    # còn nhét vào `text_query` (gói P62/P63).
    cu = session.scalar(
        select(Classification)
        .where(Classification.item_id == ma_item)
        .order_by(Classification.id.desc())
        .limit(1)
    )
    if cu is not None:
        return _xay_phan_hoi_tu_phan_loai(session, cu, ma_item)

    raw = await image.read()

    try:
        processed = preprocess_image(raw)
    except ImageValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Only ever a ProcessedImage reaches the classifier — the privacy pipeline
    # cannot be skipped from here (spec §10).
    media = _ghi_media(session, processed, raw)

    run = runs.start_run(session, kind="classify", trigger="iot")
    outcome = classify_waste(session, image_bytes=processed.content, image_phash=processed.phash)

    nhom = outcome.category
    phan_loai = Classification(
        media_id=media.id,
        text_query="",
        item_id=ma_item,
        input_type="image",
        asker_id=None,
        building_id=None,
        item_name=outcome.item_name or outcome.guess_item_name,
        items=lam_sach_gia_tri(outcome.items or [], "classifications.items"),
        predicted_category_id=nhom.id if nhom else None,
        confidence=outcome.confidence,
        tier=outcome.tier,
        model=outcome.model,
        prompt_version=outcome.prompt_version,
        refused=outcome.refused,
        refusal_reason=outcome.refusal_reason,
        escalated_to_human=outcome.refused,
        escalation_reason=outcome.escalation_reason,
        advice="",
        advice_sources=[],
        latency_ms=outcome.latency_ms,
        cost_usd=outcome.cost_usd,
        run_id=run.id,
    )
    session.add(phan_loai)
    session.flush()
    runs.finish_run(session, run, nodes=outcome.nodes)

    # A capture may carry a fill reading; recording it is best-effort and must
    # never fail the classification response. Truyền `session` để ghi xuống CSDL
    # thật (tham số tuỳ chọn của `bin_readings.record_reading`).
    if fill_percent is not None and 0.0 <= fill_percent <= 100.0:
        try:
            bin_readings.record_reading(
                bin_code=bin_code,
                device_id=device_id,
                fill_percent=fill_percent,
                is_full=False,
                uptime_s=uptime_s,
                session=session,
            )
        except ValueError:
            pass

    phan_hoi = dung_phan_hoi(outcome, item_id=ma_item)
    ket_qua = _xay_phan_hoi(processed, phan_hoi, outcome)

    # Gắn kết quả vào phiên bỏ rác đang mở của thùng (P63). Không có phiên KHÔNG
    # phải là lỗi — thiết bị vẫn chạy như thường, chỉ là không ai được điểm.
    # Ghi nhận phiên hỏng KHÔNG được làm hỏng phản hồi phân loại.
    try:
        thung = session.scalar(select(Bin).where(Bin.code == bin_code))
        if thung is not None:
            phien = phien_thung.phien_dang_mo_cua_thung(session, thung.id)
            if phien is not None:
                phien_thung.ghi_nhan_vat(session, phien, outcome)
                ket_qua["ma_phien"] = phien.ma_phien
                ket_qua["so_vat"] = phien.so_vat
        else:
            logger.info("iot/captures: không tìm thấy thùng '%s' — bỏ qua phiên.", bin_code)
    except Exception as exc:  # noqa: BLE001 - tính điểm không được làm dừng dây chuyền
        logger.warning("Gắn kết quả vào phiên thùng lỗi (%s) — vẫn trả kết quả phân loại.", exc)

    return ket_qua


def _ghi_media(session: Session, processed, raw: bytes) -> Media:
    """Ghi một ``Media`` cho ảnh thiết bị — ``uploader_id=None`` (không có tài khoản).

    Ảnh đã qua ``image_privacy.preprocess_image`` (tước EXIF, làm mờ mặt) nằm trong
    ``processed.content``; ghi xuống đĩa rồi đẩy lên ``luu_tru`` như đường người
    dùng trong ``classify.py`` — `storage_key` rỗng nếu cờ storage tắt (đĩa là lui).
    """
    settings = get_settings()
    root = Path(settings.media_dir)
    root.mkdir(parents=True, exist_ok=True)

    stem = f"{datetime.now(UTC):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:12]}"
    stored_file = root / f"{stem}.jpg"
    stored_file.write_bytes(processed.content)

    thu_muc_ngay = f"uploads/{datetime.now(UTC):%Y/%m/%d}"
    khoa_da_xu_ly = f"{thu_muc_ngay}/{stored_file.name}"

    media = Media(
        uploader_id=None,
        stored_path=str(stored_file),
        original_path="",
        storage_key=tai_len(str(stored_file), khoa_da_xu_ly) or "",
        original_storage_key="",
        phash=processed.phash,
        width=processed.width,
        height=processed.height,
        bytes_size=processed.size_bytes,
        original_width=0,
        original_height=0,
        original_bytes_size=len(raw),
        exif_stripped=processed.exif_stripped,
        faces_blurred=processed.faces_blurred or 0,
        removed_fields=[],
        expires_at=None,
    )
    session.add(media)
    session.flush()
    return media


def _trang_thai_tu_outcome(outcome: ClassifyOutcome) -> str:
    """Bản đồ kết quả phân loại 4 tầng về trạng thái hợp đồng thiết bị.

    ``ok`` · ``hazard`` (nhóm nguy hại) · ``refused`` (từ chối / không chắc).
    Không dùng ``warning``/``error`` — pipeline hiện tại không sinh ra chúng.
    """
    if outcome.refused or outcome.category is None:
        return "refused"
    if outcome.category.is_hazardous:
        return "hazard"
    return "ok"


def _xay_phan_hoi(processed, phan_hoi: dict, outcome: ClassifyOutcome) -> dict:
    """Ghép hợp đồng CP2 (từ ``dung_phan_hoi``) với mọi trường hợp đồng cũ.

    ⛔ Giữ NGUYÊN các trường firmware đang dựa vào: ``status``, ``label``,
    ``confidence``, ``requires_review``, ``message``, ``capture_id``, ``phash``,
    ``image_bytes``, ``faces_blurred``, ``exif_stripped`` — thêm vào, không thay thế.
    """
    return {
        "status": _trang_thai_tu_outcome(outcome),
        "label": phan_hoi["label"],
        "confidence": phan_hoi["confidence"],
        "requires_review": phan_hoi["review_required"],
        "message": outcome.refusal_headline_vi or "Đã phân loại.",
        "capture_id": str(uuid.uuid4()),
        "phash": processed.phash,
        "image_bytes": processed.size_bytes,
        "faces_blurred": processed.faces_blurred,
        "exif_stripped": processed.exif_stripped,
        "route": phan_hoi["route"],
        "item_id": phan_hoi["item_id"],
        "review_required": phan_hoi["review_required"],
        "model_version": phan_hoi["model_version"],
    }


def _xay_phan_hoi_tu_phan_loai(session: Session, phan_loai: Classification, ma_item: str) -> dict:
    """Dựng lại phản hồi CP2 từ bản ghi ``Classification`` cũ (idempotency).

    Cùng ``item_id`` gửi lại → trả đúng kết quả lần đầu, không tạo bản ghi thứ hai.
    Toạ độ/privacy ảnh lấy từ ``Media`` liên kết; nhãn/route từ nhóm dự đoán.
    """
    nhom = session.get(WasteCategory, phan_loai.predicted_category_id) if phan_loai.predicted_category_id else None
    outcome = ClassifyOutcome(
        category=nhom,
        confidence=phan_loai.confidence,
        refused=phan_loai.refused,
        refusal_reason=phan_loai.refusal_reason,
        prompt_version=phan_loai.prompt_version,
        model=phan_loai.model,
        item_name=phan_loai.item_name,
    )
    media = session.get(Media, phan_loai.media_id) if phan_loai.media_id else None

    class _Anh:
        pass

    anh = _Anh()
    anh.phash = media.phash if media else ""
    anh.size_bytes = media.bytes_size if media else 0
    anh.faces_blurred = media.faces_blurred if media else None
    anh.exif_stripped = media.exif_stripped if media else True

    return _xay_phan_hoi(anh, dung_phan_hoi(outcome, item_id=ma_item), outcome)


@router.post("/iot/heartbeat", response_model=HeartbeatResponse)
async def heartbeat(
    payload: HeartbeatRequest,
    authenticated_device: str = Depends(require_device_key),
) -> HeartbeatResponse:
    """Confirm to a device that the backend is reachable (IoT Checkpoint 1 §21).

    Stateless on purpose: it stores nothing. Its only job is to let a bin
    distinguish "my Wi-Fi is up" from "the backend is actually answering", which
    is the difference the device cannot work out on its own.
    """
    if payload.device_id != authenticated_device:
        raise HTTPException(status_code=401, detail="Invalid device credentials")

    return HeartbeatResponse(
        status="ok",
        device_id=authenticated_device,
        server_time=datetime.now(UTC),
    )
