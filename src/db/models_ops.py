"""Vận hành và kiểm toán: agent run, số liệu node, nhật ký audit."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models_base import Base, utcnow


class AgentRun(Base):
    """Một lần chạy pipeline agent. Gốc của màn Agent Run / Trace trên UI."""

    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), default="classify")  # classify | schedule | batch_eval
    trigger: Mapped[str] = mapped_column(String(30), default="manual")
    status: Mapped[str] = mapped_column(String(20), default="running", index=True)
    items_processed: Mapped[int] = mapped_column(default=0)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    duration_ms: Mapped[int] = mapped_column(default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    is_seed: Mapped[bool] = mapped_column(default=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    nodes: Mapped[list[RunNodeMetric]] = relationship(back_populates="run", cascade="all, delete-orphan")


class RunNodeMetric(Base):
    """Số liệu một node trong một lần chạy: độ trễ, lỗi, chi phí."""

    __tablename__ = "run_node_metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    node: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(20), default="ok")
    duration_ms: Mapped[int] = mapped_column(default=0)
    tokens_in: Mapped[int] = mapped_column(default=0)
    tokens_out: Mapped[int] = mapped_column(default=0)
    image_tokens: Mapped[int] = mapped_column(default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    cache_hits: Mapped[int] = mapped_column(default=0)
    llm_calls: Mapped[int] = mapped_column(default=0)
    retries: Mapped[int] = mapped_column(default=0)
    error_type: Mapped[str] = mapped_column(String(80), default="")
    meta: Mapped[dict] = mapped_column(JSON, default=dict)

    run: Mapped[AgentRun] = relationship(back_populates="nodes")


class AuditLog(Base):
    """Nhật ký kiểm toán cho mọi hành động rủi ro hoặc chạm dữ liệu nhạy cảm."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(60), index=True)
    entity: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[str] = mapped_column(String(60), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class BatchGanNhan(Base):
    """Một lô ảnh gom lại để gán nhãn và huấn luyện lại (dùng ở P74).

    Ảnh được gán vào lô qua `media.batch_id`. Lô có thể ở trạng thái mở (thu
    thập ảnh), đóng (không thêm ảnh nữa), hoặc đã gán nhãn xong.
    """

    __tablename__ = "batch_gan_nhan"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Ví dụ: BATCH-2026-08-20-01. Unique để không tạo trùng lô trong cùng ngày.
    ma: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    # mo | dong | da_gan_nhan
    trang_thai: Mapped[str] = mapped_column(String(20), default="mo", index=True)
    # app | thiet_bi | hon_hop
    nguon: Mapped[str] = mapped_column(String(20), default="", index=True)
    so_anh: Mapped[int] = mapped_column(default=0)
    ghi_chu: Mapped[str] = mapped_column(Text, default="")
    # NULL = lô tạo bởi hệ thống, không chỉ đích danh người tạo.
    nguoi_tao_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    # Thời điểm lô được đóng.
    dong_luc: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
