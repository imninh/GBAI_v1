"""Người dùng và địa điểm: tài khoản, toà nhà, căn hộ."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models_base import Base, utcnow


class Organization(Base):
    """Đơn vị thu gom — khách hàng chính của sản phẩm.

    Một đơn vị vận hành một chuỗi điểm thu gom: có nhân viên của mình, có thùng
    của mình. Hệ thống hiện chạy với **đúng một** đơn vị (`GreenBin Demo`), và
    cột ``organization_id`` trên ``users`` / ``bins`` mới chỉ để **ghi nhận
    thuộc về ai** — chưa có truy vấn nào lọc theo nó.
    """

    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str] = mapped_column(String(300), default="")
    phone: Mapped[str] = mapped_column(String(20), default="")
    is_active: Mapped[bool] = mapped_column(default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class User(Base):
    """Người dùng hệ thống.

    Ba vai trò, trong đó ``resident`` và ``manager`` là hai vai trò bắt buộc
    theo yêu cầu tối thiểu của chương trình; ``cleaner`` là đội vệ sinh.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    # Định danh đăng nhập chính từ gói G1. CỐ TÌNH không đặt `unique=True`: các
    # dòng có sẵn nhận giá trị rỗng sau khi vá cột, mà unique trên chuỗi rỗng là
    # đụng nhau ngay. Tính duy nhất ép ở tầng dịch vụ lúc đăng ký.
    phone: Mapped[str] = mapped_column(String(20), default="", index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20), index=True)  # resident | cleaner | manager
    password_hash: Mapped[str] = mapped_column(String(255))
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id"), nullable=True)
    # Nơi ở là HAI khái niệm khác nhau:
    #   * `unit_id` — QUAN HỆ HÀNH CHÍNH: thuộc toà nào, BQL nào duyệt, lịch nào
    #     áp. Có giá trị khi người này là cư dân chung cư của một toà trong hệ
    #     thống (liên kết toà qua `Unit.building_id`).
    #   * `address` / `lat` / `lng` — TOẠ ĐỘ ĐỊA LÝ: xe đi đến đâu để lấy hàng.
    #     Cột riêng cho 600 tài khoản nhập từ dữ liệu GIS là hộ dân lẻ trên phố:
    #     có địa chỉ và toạ độ rõ ràng nhưng không thuộc căn hộ nào. Không đẻ căn
    #     hộ giả cho họ (gói P52).
    # Ưu tiên quyết định "người này ở đâu" tập trung ở `src/services/noi_o.py`,
    # không được rải `if user.unit_id is None` ra router hay serializer.
    address: Mapped[str] = mapped_column(String(300), default="")
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Đơn vị thu gom mà người này thuộc về. NULL = chưa gắn tổ chức nào — trạng
    # thái của mọi tài khoản có từ trước, và của cư dân (cư dân không thuộc đơn
    # vị thu gom nào).
    #
    # ⚠️ CHƯA CÓ CHỖ NÀO LỌC THEO CỘT NÀY. Đây mới là nền dữ liệu; việc tách dữ
    # liệu giữa các đơn vị là gói A1b. Đừng tưởng có cột là đã có bảo vệ.
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    green_points: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Building(Base):
    """Toà nhà. Quy định phân loại và lịch thu gom khác nhau giữa các toà."""

    __tablename__ = "buildings"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str] = mapped_column(String(300), default="")
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Unit(Base):
    """Căn hộ."""

    __tablename__ = "units"

    id: Mapped[int] = mapped_column(primary_key=True)
    building_id: Mapped[int] = mapped_column(ForeignKey("buildings.id"), index=True)
    code: Mapped[str] = mapped_column(String(30))

    building: Mapped[Building] = relationship()
