"""Kho tri thức (RAG): tài liệu nguồn và các đoạn đã cắt."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.db.models_base import Base, utcnow


class KnowledgeDoc(Base):
    """Tài liệu nguồn: quy định pháp luật, nội quy toà nhà, lịch thu gom."""

    __tablename__ = "knowledge_docs"

    id: Mapped[int] = mapped_column(primary_key=True)
    building_id: Mapped[int | None] = mapped_column(ForeignKey("buildings.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(300))
    source: Mapped[str] = mapped_column(String(300), default="")
    doc_type: Mapped[str] = mapped_column(String(40), default="")  # law | building_rule | schedule | hazard
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class KnowledgeChunk(Base):
    """Đoạn văn bản đã cắt để truy hồi.

    ``embedding`` lưu dạng JSON list cho SQLite. Khi chuyển sang PostgreSQL
    thì đổi sang kiểu ``vector`` của pgvector, phần còn lại giữ nguyên.
    """

    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    doc_id: Mapped[int] = mapped_column(ForeignKey("knowledge_docs.id"), index=True)
    content: Mapped[str] = mapped_column(Text)
    section: Mapped[str] = mapped_column(String(200), default="")
    embedding: Mapped[list] = mapped_column(JSON, default=list)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
