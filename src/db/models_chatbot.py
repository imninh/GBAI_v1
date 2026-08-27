"""Mô hình dữ liệu cho phiên hội thoại và tin nhắn Chatbot RAG (Multi-turn State & Tool Idempotency)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models_base import Base, utcnow


class ChatSession(Base):
    """Phiên hội thoại đa lượt của cư dân với Chatbot."""

    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    building_id: Mapped[int | None] = mapped_column(ForeignKey("buildings.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), default="Hội thoại mới")
    working_memory: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    messages: Mapped[list[ChatMessage]] = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan", order_by="ChatMessage.id")


class ChatMessage(Base):
    """Từng tin nhắn trong phiên hội thoại đa lượt."""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # user | assistant | tool | system
    content: Mapped[str] = mapped_column(Text)
    intent: Mapped[str] = mapped_column(String(50), default="out_of_scope")
    sources_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    tool_calls_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    session: Mapped[ChatSession] = relationship("ChatSession", back_populates="messages")


class ToolExecutionRecord(Base):
    """Ghi nhận thực thi tool với Idempotency Key để chống gọi trùng lặp (TTL / Deduplication)."""

    __tablename__ = "tool_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    tool_name: Mapped[str] = mapped_column(String(100))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="COMPLETED")  # PENDING | COMPLETED | FAILED
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
