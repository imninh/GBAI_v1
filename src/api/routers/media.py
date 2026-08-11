"""Ảnh và quyền riêng tư.

Ảnh cư dân **không bao giờ đặt ở URL công khai đoán được** — mọi lượt xem đều
đi qua endpoint có kiểm quyền. Ảnh gốc chỉ ban quản lý mở được, và mỗi lần mở
đều ghi ``AuditLog``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from src.api.deps import CurrentUser, DbSession, require
from src.api.errors import ApiError, forbidden, not_found
from src.api.serializers import media_privacy_dict
from src.db.models import Media, User
from src.services.auth import write_audit

router = APIRouter(prefix="/media", tags=["media"])


def _load(session, media_id: int) -> Media:
    media = session.get(Media, media_id)
    if media is None:
        raise not_found("ảnh này")
    return media


def _can_see(user: User, media: Media) -> bool:
    """Chủ ảnh xem được ảnh mình; đội vệ sinh và BQL xem được để làm việc."""
    return media.uploader_id == user.id or user.role in {"cleaner", "manager"}


@router.get("/{media_id}")
def get_media(media_id: int, session: DbSession, user: CurrentUser) -> FileResponse:
    """Ảnh **đã xử lý** (đã tước EXIF, đã làm mờ mặt, đã nén)."""
    media = _load(session, media_id)
    if not _can_see(user, media):
        raise forbidden("Bạn chỉ xem được ảnh của chính mình.")
    path = Path(media.stored_path)
    if not path.exists():
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
) -> FileResponse:
    """Ảnh gốc chưa xử lý — chỉ ban quản lý, và luôn ghi nhật ký kiểm toán."""
    media = _load(session, media_id)
    if not media.original_path:
        raise not_found("ảnh gốc của ảnh này")
    path = Path(media.original_path)
    if not path.exists():
        raise ApiError(410, "IMG-410", "Ảnh gốc đã bị xoá theo hạn lưu trữ.")

    write_audit(
        session,
        actor=user,
        action="view_original_media",
        entity="media",
        entity_id=str(media.id),
        detail={"uploader_id": media.uploader_id},
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

    for attribute in ("stored_path", "original_path"):
        raw = getattr(media, attribute, "")
        if raw:
            Path(raw).unlink(missing_ok=True)
    media.stored_path = ""
    media.original_path = ""
    session.flush()

    write_audit(session, actor=user, action="delete_media", entity="media", entity_id=str(media.id))
    return {"ok": True, "message_vi": "Đã xoá ảnh khỏi hệ thống."}
