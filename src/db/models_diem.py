"""Sổ cái điểm thưởng — nguồn sự thật của ``users.green_points``."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.db.models_base import Base, utcnow


class DiemThuongLog(Base):
    """Sổ cái điểm thưởng — mỗi dòng là MỘT lần trao điểm, không bao giờ sửa.

    ``users.green_points`` chỉ là con số tổng để hiện nhanh; **bảng này mới là
    nguồn sự thật**. Có sổ cái thì mới trả lời được "điểm này từ đâu ra", mới
    kiểm toán được, và sau này mới trừ điểm khi đổi quà một cách an toàn.

    ``request_id`` là **duy nhất**: một yêu cầu thu gom chỉ được trao điểm đúng
    một lần, kể cả khi ai đó gọi lại hàm xác nhận.
    """

    __tablename__ = "diem_thuong_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # NULL cho phép các loại trao điểm không gắn với yêu cầu thu gom (đổi quà…).
    request_id: Mapped[int | None] = mapped_column(
        ForeignKey("pickup_requests.id"), nullable=True, unique=True, index=True
    )
    diem: Mapped[int] = mapped_column(default=0)
    diem_khoi_luong: Mapped[int] = mapped_column(default=0)
    diem_vat_lieu: Mapped[int] = mapped_column(default=0)
    # Số cân NGƯỜI xác nhận — chép lại để sổ cái tự giải thích được, không phải
    # đi tra ngược về yêu cầu mỗi lần.
    weight_confirmed_kg: Mapped[float] = mapped_column(Float, default=0.0)
    # Bóc tách theo từng mã nhóm rác: {ma: {"so_mon": n, "diem": d}}.
    chi_tiet: Mapped[dict] = mapped_column(JSON, default=dict)
    ly_do: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
