"""Thùng thu gom thông minh: thùng và lịch sử báo cáo."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models_base import Base, utcnow


class Bin(Base):
    """Một thùng thu gom thông minh đặt ngoài hiện trường.

    Thùng định kỳ báo về mức rác (``fill_percent``) và mức pin
    (``battery_percent``). Con số mới nhất lưu ngay trên ``Bin`` cho màn điều
    phối; toàn bộ lịch sử lưu trên ``BinReading``. ``building_id`` cho phép
    NULL vì thùng đặt ngoài đường không thuộc toà nào.
    """

    __tablename__ = "bins"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    building_id: Mapped[int | None] = mapped_column(ForeignKey("buildings.id"), nullable=True, index=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    address: Mapped[str] = mapped_column(String(300), default="")
    # Mã nhóm rác thùng này nhận, ví dụ ["recyclable_plastic", "recyclable_paper"].
    category_codes: Mapped[list] = mapped_column(JSON, default=list)
    capacity_liters: Mapped[float] = mapped_column(Float, default=0.0)
    # Bộ dữ liệu GIS Hà Nội (gói P30) mang theo năm thông tin của một vị trí đề
    # xuất — thùng còn là ứng viên chứ chưa phải hạ tầng đã triển khai.
    site_type: Mapped[str] = mapped_column(String(40), default="")
    priority: Mapped[str] = mapped_column(String(8), default="")
    deployment_status: Mapped[str] = mapped_column(String(20), default="")
    coordinate_confidence: Mapped[str] = mapped_column(String(10), default="")
    # Tên khu vực để hiển thị và gom nhóm. Hà Nội đã tổ chức lại đơn vị cấp xã
    # từ 01/07/2025 thành 126 đơn vị (51 phường, 75 xã), nên cột này CHỈ để
    # hiển thị và gom nhóm, KHÔNG BAO GIỜ làm khoá hành chính. Chính nguồn dữ
    # liệu cũng khuyến cáo đúng điều đó.
    area_name: Mapped[str] = mapped_column(String(60), default="", index=True)
    fill_percent: Mapped[float] = mapped_column(Float, default=0.0)
    battery_percent: Mapped[float] = mapped_column(Float, default=0.0)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, index=True)
    is_seed: Mapped[bool] = mapped_column(default=False, index=True)
    # Nhân viên vệ sinh được giao thùng này. NULL = chưa gán ai: ban quản lý vẫn
    # thấy, nhân viên thì không (phần lọc nằm ở gói A2b). Cột cho phép NULL vì
    # mọi thùng đang có trong CSDL đều chưa gán, và vì thùng đặt ngoài đường có
    # thể tạm thời không thuộc ai.
    assigned_cleaner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    # Khoá riêng của thiết bị gắn trên thùng này, lưu dạng BĂM — chuỗi thô chỉ
    # hiện đúng một lần lúc cấp, hệ thống không giữ lại được.
    # Rỗng = thùng chưa được cấp khoá riêng, vẫn dùng khoá chung `BIN_DEVICE_KEY`.
    device_key_hash: Mapped[str] = mapped_column(String(64), default="")
    # Đơn vị thu gom sở hữu thùng này. NULL = chưa gắn tổ chức nào.
    # ⚠️ CHƯA CÓ CHỖ NÀO LỌC THEO CỘT NÀY — xem chú thích ở `User.organization_id`.
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    readings: Mapped[list[BinReading]] = relationship(back_populates="bin", cascade="all, delete-orphan")


class BinReading(Base):
    """Một lần thùng báo về mức rác và mức pin.

    ``source``: ``device`` (thiết bị thật) | ``simulator`` (mô phỏng) |
    ``manual`` (nhập tay).
    """

    __tablename__ = "bin_readings"

    id: Mapped[int] = mapped_column(primary_key=True)
    bin_id: Mapped[int] = mapped_column(ForeignKey("bins.id"), index=True)
    fill_percent: Mapped[float] = mapped_column(Float)
    battery_percent: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    bin: Mapped[Bin] = relationship(back_populates="readings")
