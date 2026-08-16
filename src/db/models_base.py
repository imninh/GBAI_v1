"""Nền tảng của mọi bảng — ``Base`` và ``utcnow`` dùng chung.

Tách riêng để các module theo miền nghiệp vụ chỉ cần import ``Base`` từ đây,
đảm bảo **một** ``DeclarativeBase`` duy nhất cho toàn bộ metadata (``create_all``
chạy trên đúng ``Base.metadata`` tổng hợp mọi bảng).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import DeclarativeBase


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass
