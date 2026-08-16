"""Lịch thu gom, cảnh báo và thông báo."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.db.models_base import Base, utcnow


class CollectionSchedule(Base):
    """Lịch thu gom theo nhóm rác của từng toà.

    Hướng dẫn "bỏ ở đâu, thu gom lúc nào" chỉ đúng với toà đang chọn — đây là
    bảng làm cho câu đó đúng, và là dữ liệu cho màn Lịch xem được offline.
    """

    __tablename__ = "collection_schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    building_id: Mapped[int] = mapped_column(ForeignKey("buildings.id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), index=True)
    weekdays: Mapped[list] = mapped_column(JSON, default=list)  # 0=Thứ 2 … 6=Chủ nhật
    window: Mapped[str] = mapped_column(String(30), default="")  # "18:00-20:00"
    location: Mapped[str] = mapped_column(String(200), default="")


class Alert(Base):
    """Cảnh báo hiện trên dải đầu màn Tổng quan của BQL."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    severity: Mapped[str] = mapped_column(String(20), default="info", index=True)  # critical | warning | info
    title: Mapped[str] = mapped_column(String(300))
    building_id: Mapped[int | None] = mapped_column(ForeignKey("buildings.id"), nullable=True, index=True)
    entity: Mapped[str] = mapped_column(String(60), default="")
    entity_id: Mapped[str] = mapped_column(String(60), default="")
    threshold: Mapped[str] = mapped_column(String(120), default="")
    ack: Mapped[bool] = mapped_column(default=False, index=True)
    ack_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    is_seed: Mapped[bool] = mapped_column(default=False, index=True)
    triggered_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Notification(Base):
    """Thông báo gửi cho cư dân / đội vệ sinh khi có quyết định của người duyệt."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    entity: Mapped[str] = mapped_column(String(60), default="")
    entity_id: Mapped[str] = mapped_column(String(60), default="")
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
