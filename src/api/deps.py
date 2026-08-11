"""Dependency dùng chung cho các router: phiên CSDL, người dùng, kiểm quyền."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from src.api.errors import ApiError, forbidden
from src.db.models import User
from src.db.session import get_session_factory
from src.services.auth import PERMISSION_DENIED_HINTS, AuthError, can, decode_token


def get_db() -> Iterator[Session]:
    """Mở một phiên CSDL cho mỗi request, commit khi thành công."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    session: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    """Đọc JWT từ header ``Authorization: Bearer <token>``.

    Raises:
        ApiError: 401 khi thiếu token, token hỏng, hoặc người dùng không còn tồn tại.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ApiError(401, "AUTH-401", "Bạn cần đăng nhập để dùng chức năng này.")

    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
    except AuthError as exc:
        raise ApiError(401, exc.code, exc.message_vi) from exc

    user = session.get(User, int(payload.get("sub", 0) or 0))
    if user is None:
        raise ApiError(401, "AUTH-401", "Tài khoản không còn tồn tại.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require(permission: str):
    """Tạo dependency kiểm một quyền cụ thể.

    Dùng như ``Depends(require("review_pickup"))``.
    """

    def _check(user: CurrentUser) -> User:
        if not can(user, permission):
            raise forbidden(PERMISSION_DENIED_HINTS.get(permission, "Vai trò của bạn không có quyền này."))
        return user

    return _check
