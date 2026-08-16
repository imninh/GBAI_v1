"""Ảnh và quyền riêng tư.

Ảnh cư dân **không bao giờ đặt ở URL công khai đoán được** — mọi lượt xem đều
đi qua endpoint có kiểm quyền. Ảnh gốc chỉ ban quản lý mở được, và mỗi lần mở
đều ghi ``AuditLog``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse, Response

from src.api.deps import CurrentUser, DbSession, require
from src.api.errors import ApiError, bad_request, forbidden, not_found
from src.api.serializers import media_privacy_dict
from src.db.models import Media, User
from src.services.auth import write_audit
from src.services.image import preprocess_image
from src.services.luu_tru import tai_len, tai_ve, xoa

router = APIRouter(prefix="/media", tags=["media"])

MAX_UPLOAD_BYTES = 12 * 1024 * 1024


def _load(session, media_id: int) -> Media:
    media = session.get(Media, media_id)
    if media is None:
        raise not_found("ảnh này")
    return media


def _can_see(user: User, media: Media) -> bool:
    """Chủ ảnh xem được ảnh mình; đội vệ sinh và BQL xem được để làm việc."""
    return media.uploader_id == user.id or user.role in {"cleaner", "manager"}


@router.post("")
async def upload_media(
    session: DbSession,
    user: CurrentUser,
    image: Annotated[UploadFile, File()],
) -> dict:
    """Tải một ảnh, tiền xử lý (tước EXIF · làm mờ mặt · nén 512px), trả ``media_id``.

    Dùng cho wizard thu gom đính ảnh từng món — KHÔNG chạy phân loại. Cùng pipeline
    ẩn danh với ``/classify`` để ảnh nào vào hệ thống cũng đã được làm sạch.
    """
    raw = await image.read()
    if not raw:
        raise bad_request("File ảnh rỗng.", code="IMG-400")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise bad_request("Ảnh quá lớn, tối đa 12 MB.", code="IMG-413")
    try:
        processed = preprocess_image(raw)
    except ValueError as exc:
        raise bad_request("Mình không đọc được file ảnh này.", code="IMG-415") from exc

    hom_nay = datetime.now(UTC)
    thu_muc_ngay = f"uploads/{hom_nay:%Y/%m/%d}"
    khoa_da_xu_ly = f"{thu_muc_ngay}/{Path(processed.stored_path).name}"
    khoa_goc = f"{thu_muc_ngay}/{Path(processed.original_path).name}" if processed.original_path else ""

    media = Media(
        uploader_id=user.id,
        stored_path=processed.stored_path,
        original_path=processed.original_path,
        storage_key=tai_len(processed.stored_path, khoa_da_xu_ly) or "",
        original_storage_key=tai_len(processed.original_path, khoa_goc) if processed.original_path else "",
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
    return {"media_id": media.id}


@router.get("/{media_id}")
def get_media(media_id: int, session: DbSession, user: CurrentUser) -> Response:
    """Ảnh **đã xử lý** (đã tước EXIF, đã làm mờ mặt, đã nén)."""
    media = _load(session, media_id)
    if not _can_see(user, media):
        raise forbidden("Bạn chỉ xem được ảnh của chính mình.")
    # Ưu tiên Storage: có khoá thì đọc từ đó; `tai_ve` trả `None` (tắt cờ / hỏng /
    # quá hạn) thì rơi về đĩa y như hôm nay. Cả hai đều không có → 410 như cũ.
    if media.storage_key:
        noi_dung = tai_ve(media.storage_key)
        if noi_dung is not None:
            return Response(content=noi_dung, media_type="image/jpeg")
    path = Path(media.stored_path)
    # `Path("")` trỏ về "." (tồn tại thật) nên phải chặn chuỗi rỗng trước khi
    # kiểm tồn tại — nếu không `FileResponse(".")` nổ RuntimeError thay vì 410.
    if not media.stored_path or not path.exists():
        raise ApiError(410, "IMG-410", "Ảnh đã hết hạn lưu trữ và được xoá tự động.")
    return FileResponse(path, media_type="image/jpeg")


@router.get("/{media_id}/privacy")
def get_privacy_report(media_id: int, session: DbSession, user: CurrentUser) -> dict:
    """Bảng đối chiếu "ảnh gốc / đã gửi đi" cho màn 4.5."""
    media = _load(session, media_id)
    if not _can_see(user, media):
        raise forbidden("Bạn chỉ xem được ảnh của chính mình.")
    return media_privacy_dict(media)


@router.get("/{media_id}/original")
def get_original(
    media_id: int,
    session: DbSession,
    user: Annotated[User, Depends(require("view_original_media"))],
) -> Response:
    """Ảnh gốc chưa xử lý — chỉ ban quản lý, và luôn ghi nhật ký kiểm toán."""
    media = _load(session, media_id)
    if not media.original_path and not media.original_storage_key:
        raise not_found("ảnh gốc của ảnh này")
    if media.original_storage_key:
        noi_dung = tai_ve(media.original_storage_key)
        if noi_dung is not None:
            write_audit(
                session,
                actor=user,
                action="view_original_media",
                entity="media",
                entity_id=str(media.id),
                detail={"uploader_id": media.uploader_id, "nguon": "storage"},
            )
            return Response(content=noi_dung, media_type="image/jpeg")
    path = Path(media.original_path)
    if not path.exists():
        raise ApiError(410, "IMG-410", "Ảnh gốc đã bị xoá theo hạn lưu trữ.")

    write_audit(
        session,
        actor=user,
        action="view_original_media",
        entity="media",
        entity_id=str(media.id),
        detail={"uploader_id": media.uploader_id, "nguon": "dia"},
    )
    return FileResponse(path, media_type="image/jpeg")


@router.delete("/{media_id}")
def delete_media(media_id: int, session: DbSession, user: CurrentUser) -> dict:
    """Cư dân bấm "Xoá ngay" trên màn quyền riêng tư.

    Xoá file trên đĩa, giữ lại bản ghi để số liệu vận hành không bị hụt.
    """
    media = _load(session, media_id)
    if media.uploader_id != user.id and user.role != "manager":
        raise forbidden("Bạn chỉ xoá được ảnh của chính mình.")

    # Xoá file trên Storage (nếu có khoá). Storage xoá hỏng KHÔNG được làm hỏng
    # cả lệnh xoá — `xoa` trả False rồi đi tiếp, không ném ngoại lệ.
    for attribute, khoa in (("stored_path", media.storage_key), ("original_path", media.original_storage_key)):
        raw = getattr(media, attribute, "")
        if raw:
            Path(raw).unlink(missing_ok=True)
        if khoa:
            xoa(khoa)
    media.stored_path = ""
    media.original_path = ""
    media.storage_key = ""
    media.original_storage_key = ""
    session.flush()

    write_audit(session, actor=user, action="delete_media", entity="media", entity_id=str(media.id))
    return {"ok": True, "message_vi": "Đã xoá ảnh khỏi hệ thống."}
