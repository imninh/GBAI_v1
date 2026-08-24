"""Sổ cái điểm thưởng — nguồn sự thật của ``users.green_points``."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
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


class DiemNhanThucLog(Base):
    """Sổ cái điểm NHẬN THỨC — điểm của tầng app, tách hẳn khỏi ``diem_thuong_log``.

    Dùng cho gói **P79 (hệ điểm nhận thức)**: ghi lại từng lần nhận điểm nhận
    thức của cư dân từ các nguồn ``chup_anh`` · ``phien_thung`` · ``nhiem_vu_ngay``
    · ``nhiem_vu_tuan``. Tổng điểm nhận thức của một người **tính bằng ``SUM``
    trên sổ cái này**, không có cột tổng trên ``users`` (cột tổng là dữ liệu
    nhân bản, sẽ lệch).

    ⛔ LUẬT CỨNG CỦA DỰ ÁN: điểm nhận thức **KHÔNG quy đổi thành quà**; chỉ
    ``diem_thuong_log`` (và ``users.green_points``) mới là **điểm có giá trị**,
    đổi được quà. Hai tầng này không bao giờ được trộn lẫn. Đừng thêm cột hay
    logic quy đổi nào cả.
    """

    __tablename__ = "diem_nhan_thuc_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # chup_anh | phien_thung | nhiem_vu_ngay | nhiem_vu_tuan
    nguon: Mapped[str] = mapped_column(String(30), index=True)
    diem: Mapped[int] = mapped_column(Integer, default=0)
    # Tên bảng của bản ghi gốc (ví dụ "classifications") — để tra ngược.
    ref_bang: Mapped[str] = mapped_column(String(40), default="")
    # Id bản ghi gốc — NULL khi không gắn với bản ghi cụ thể nào.
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Ngày ghi nhận, dùng để tính trần mỗi ngày.
    ngay: Mapped[date] = mapped_column(Date, index=True)
    ghi_chu: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class NhiemVu(Base):
    """Danh mục nhiệm vụ dùng cho gói **P79 (hệ điểm nhận thức)**.

    Mỗi nhiệm vụ có chu kỳ ``ngay`` hoặc ``tuan``, một điều kiện đếm (ví dụ
    ``so_lan_phan_loai`` đạt ngưỡng ``3``) và phần thưởng điểm nhận thức. Gói
    P79 đọc bảng này để biết "ai làm gì đủ điều kiện thì trao bao nhiêu điểm",
    ghi vào ``DiemNhanThucLog`` và đánh dấu ở ``NhiemVuHoanThanh``. Bảng này
    chỉ là danh mục tĩnh — gói này KHÔNG seed dữ liệu.
    """

    __tablename__ = "nhiem_vu"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Mã nhiệm vụ, ví dụ "NGAY_PHAN_LOAI_3_MON".
    ma: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    ten: Mapped[str] = mapped_column(String(200))
    mo_ta: Mapped[str] = mapped_column(Text, default="")
    # ngay | tuan
    chu_ky: Mapped[str] = mapped_column(String(10), index=True)
    # Mã điều kiện, ví dụ "so_lan_phan_loai".
    dieu_kien_ma: Mapped[str] = mapped_column(String(40))
    dieu_kien_nguong: Mapped[int] = mapped_column(Integer, default=0)
    diem: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class NhiemVuHoanThanh(Base):
    """Ai đã nhận nhiệm vụ nào, kỳ nào — dùng cho gói **P79 (hệ điểm nhận thức)**.

    Ghi lại mỗi lần một người hoàn thành một nhiệm vụ trong một kỳ (``2026-08-21``
    cho nhiệm vụ ngày, ``2026-W34`` cho nhiệm vụ tuần) và điểm nhận thức đã trao.
    Ràng buộc duy nhất trên ``(user_id, nhiem_vu_id, ky)`` chặn việc một người
    nhận điểm cùng một nhiệm vụ nhiều lần trong một kỳ.
    """

    __tablename__ = "nhiem_vu_hoan_thanh"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "nhiem_vu_id", "ky", name="uq_nhiem_vu_hoan_thanh_user_ky"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    nhiem_vu_id: Mapped[int] = mapped_column(ForeignKey("nhiem_vu.id"), index=True)
    ky: Mapped[str] = mapped_column(String(20), index=True)
    diem_da_trao: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
