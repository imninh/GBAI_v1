"""Khuôn lỗi thống nhất cho toàn bộ API.

``{"error": {"code", "message_vi", "detail"}}`` — frontend hiện ``message_vi``
cho người dùng và ``code`` ở góc để đối chiếu log. Không bao giờ trả stack trace
ra ngoài.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


class ApiError(HTTPException):
    """Lỗi có mã và câu tiếng Việt dành cho người dùng cuối."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message_vi: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=message_vi)
        self.code = code
        self.message_vi = message_vi
        self.extra = detail or {}


def error_body(code: str, message_vi: str, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message_vi": message_vi, "detail": detail or {}}}


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=error_body(exc.code, exc.message_vi, exc.extra))


async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Bọc các HTTPException còn lại vào cùng một khuôn."""
    message = exc.detail if isinstance(exc.detail, str) else "Yêu cầu không hợp lệ."
    return JSONResponse(status_code=exc.status_code, content=error_body(f"HTTP-{exc.status_code}", message))


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Lỗi ngoài dự kiến: che chi tiết kỹ thuật, giữ lại mã để tra log."""
    return JSONResponse(
        status_code=500,
        content=error_body(
            "SRV-500",
            "Hệ thống gặp sự cố ngoài dự kiến. Bạn thử lại giúp mình nhé.",
            {"type": type(exc).__name__},
        ),
    )


# Các lỗi hay dùng, gom lại để câu chữ nhất quán khắp nơi.


def not_found(entity_vi: str) -> ApiError:
    return ApiError(404, "NF-404", f"Không tìm thấy {entity_vi}.")


def forbidden(reason_vi: str) -> ApiError:
    return ApiError(403, "PERM-403", reason_vi)


def bad_request(message_vi: str, code: str = "REQ-400") -> ApiError:
    return ApiError(400, code, message_vi)
