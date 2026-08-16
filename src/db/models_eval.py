"""Eval: các lần chạy đánh giá và ca thất bại đã ghi nhận."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.db.models_base import Base, utcnow


class EvalRun(Base):
    """Một lần chạy eval trên tập test giữ riêng.

    Tách ``by_dataset`` công khai / tự chụp vì chênh lệch giữa hai bộ là một
    phát hiện đáng đưa vào báo cáo (CLAUDE.md mục 6).
    """

    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    dataset: Mapped[str] = mapped_column(String(30), default="public")  # public | own | mixed
    test_size: Mapped[int] = mapped_column(default=0)
    accuracy: Mapped[float] = mapped_column(Float, default=0.0)
    macro_f1: Mapped[float] = mapped_column(Float, default=0.0)
    hazard_recall: Mapped[float] = mapped_column(Float, default=0.0)
    # Chỉ số an toàn cốt lõi: rác nguy hại bị phân loại thành rác thường.
    hazard_missed_count: Mapped[int] = mapped_column(default=0)
    retrieval_precision_at_5: Mapped[float] = mapped_column(Float, default=0.0)
    confusion_matrix: Mapped[dict] = mapped_column(JSON, default=dict)
    prompt_version: Mapped[str] = mapped_column(String(20), default="")
    model: Mapped[str] = mapped_column(String(60), default="")
    avg_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    p95_latency_ms: Mapped[int] = mapped_column(default=0)
    is_seed: Mapped[bool] = mapped_column(default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class FailureCase(Base):
    """Một ca AI nhận sai, kèm phân loại nguyên nhân.

    Đây là lợi thế demo lớn nhất của đề: trình chiếu được ảnh thật bị nhận sai.
    """

    __tablename__ = "failure_cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    eval_run_id: Mapped[int | None] = mapped_column(ForeignKey("eval_runs.id"), nullable=True, index=True)
    classification_id: Mapped[int | None] = mapped_column(ForeignKey("classifications.id"), nullable=True)
    media_id: Mapped[int | None] = mapped_column(ForeignKey("media.id"), nullable=True)
    item_name: Mapped[str] = mapped_column(String(200), default="")
    true_category_code: Mapped[str] = mapped_column(String(40), default="")
    predicted_category_code: Mapped[str] = mapped_column(String(40), default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    # ảnh tối | nhiều vật | vật bị che | chất liệu hỗn hợp | góc chụp lạ
    cause: Mapped[str] = mapped_column(String(40), default="")
    resolved: Mapped[bool] = mapped_column(default=False)
    is_seed: Mapped[bool] = mapped_column(default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
