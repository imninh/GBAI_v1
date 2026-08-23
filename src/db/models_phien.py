"""Phiên bỏ rác tại thùng và token thiết bị nhận thông báo đẩy (gói P62).

Hai bảng này là NỀN cho gói P63 (phiên thùng) và gói thông báo đẩy — gói này chỉ
khai model, chưa có dịch vụ hay endpoint nào. ``create_all`` tự dựng lúc khởi
động nên KHÔNG cần khai vào ``COT_CAN_VA``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.db.models_base import Base, utcnow


class PhienThung(Base):
    """Một phiên bỏ rác tại thùng — người dùng mở thùng, phân loại, đóng.

    ``diem_nhan_thuc`` là ĐIỂM NHẬN THỨC: ⛔ KHÔNG được cộng vào
    ``users.green_points``. Quy tắc đã chốt: *"điểm có giá trị chỉ tính trên khối
    lượng người cân; lớp điểm nhận thức tách bạch, không quy đổi"*. Tên cột nói
    rõ điều đó để không ai nhầm về sau.
    """

    __tablename__ = "phien_thung"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Chuỗi app dùng để tham chiếu phiên — không lộ id chạy số ra ngoài.
    ma_phien: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    bin_id: Mapped[int] = mapped_column(ForeignKey("bins.id"), index=True)
    # dang_mo · da_dong · het_han · loi
    trang_thai: Mapped[str] = mapped_column(String(20), default="dang_mo", index=True)
    bat_dau: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ket_thuc: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Số vật đã phân loại và ĐƯỢC CHẤP NHẬN.
    so_vat: Mapped[int] = mapped_column(default=0)
    # Điểm nhận thức — không quy đổi, không cộng vào green_points.
    diem_nhan_thuc: Mapped[int] = mapped_column(default=0)
    # Lý do khi lỗi / hết hạn.
    ghi_chu: Mapped[str] = mapped_column(String(200), default="")


class TokenThietBi(Base):
    """Token do Firebase cấp để gửi thông báo đẩy tới một thiết bị của người dùng.

    ``created_at`` / ``last_seen`` để dọn token chết sau này — thiết bị bị gỡ app
    giữ token sống mãi thì mỗi lần gửi thông báo lại bị Firebase trả lỗi.
    """

    __tablename__ = "token_thiet_bi"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    # android · ios · web
    nen_tang: Mapped[str] = mapped_column(String(20), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MaQrThung(Base):
    """Mã QR thay đổi mỗi phiên —防伪, mã dùng một lần.

    Mỗi lần thiết bị xin mã, một mã mới được sinh ra và mã cũ chưa dùng
    của thùng đó bị vô hiệu. Mã chứa đường link web, ai quét cũng mở được
    (không cần app GreenBin).
    """

    __tablename__ = "ma_qr_thung"

    id: Mapped[int] = mapped_column(primary_key=True)
    bin_id: Mapped[int] = mapped_column(ForeignKey("bins.id"), index=True)
    ma: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    het_han_luc: Mapped[datetime] = mapped_column(DateTime, index=True)
    da_dung: Mapped[bool] = mapped_column(default=False, index=True)
    da_dung_luc: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    phien_id: Mapped[int | None] = mapped_column(ForeignKey("phien_thung.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
