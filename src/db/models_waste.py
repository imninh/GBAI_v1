"""Danh mục rác: các nhóm rác và hướng dẫn xử lý."""

from __future__ import annotations

from sqlalchemy import Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.db.models_base import Base


class WasteCategory(Base):
    """Danh mục loại rác và hướng dẫn xử lý.

    ``is_hazardous`` quyết định ngưỡng an toàn: nhóm nguy hại dùng ngưỡng
    confidence cao hơn và luôn kèm cảnh báo cố định, không để LLM tự sinh.
    """

    __tablename__ = "waste_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    parent_code: Mapped[str] = mapped_column(String(40), default="")
    is_hazardous: Mapped[bool] = mapped_column(default=False, index=True)
    # Ngưỡng confidence tối thiểu để hệ thống dám tự trả lời cho nhóm này.
    min_confidence: Mapped[float] = mapped_column(Float, default=0.6)
    bin_color: Mapped[str] = mapped_column(String(30), default="")
    handling_note: Mapped[str] = mapped_column(Text, default="")
    safety_warning: Mapped[str] = mapped_column(Text, default="")
    # Gợi ý icon cho UI. Màu KHÔNG được là kênh thông tin duy nhất (spec 2.2).
    icon: Mapped[str] = mapped_column(String(16), default="")
    sort_order: Mapped[int] = mapped_column(default=0)
    # Nhãn tiếng Anh dùng cho CLIP zero-shot ở tầng T0.5, phân cách bằng "|".
    clip_prompts: Mapped[str] = mapped_column(Text, default="")
