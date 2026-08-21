"""Thu gom: yêu cầu, timeline sự kiện, tuyến và điểm dừng."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models_base import Base, utcnow
from src.services.pickup_lifecycle import CHO_DUYET


class PickupRequest(Base):
    """Yêu cầu thu gom đồ cồng kềnh / rác tái chế khối lượng lớn.

    Vượt ngưỡng khối lượng hoặc số món thì ``requires_hitl=True`` và phải được
    BQL/đội vệ sinh xác nhận trước khi lên lịch — đúng ràng buộc của đề.
    """

    __tablename__ = "pickup_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    resident_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # Liên kết hành chính tới căn hộ — NULL khi cư dân là hộ dân lẻ (không thuộc
    # căn hộ nào) hoặc chọn điểm lấy hàng khác nơi ở. Toạ độ lấy hàng khi đó nằm
    # ở ba cột `address` / `lat` / `lng` dưới đây.
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id"), nullable=True, index=True)
    # Điểm lấy hàng của RIÊNG yêu cầu này — xe đi đến đây để lấy đồ, có thể khác
    # nơi ở đăng ký trên `users`. `address` rỗng nghĩa là không có điểm riêng
    # (lấy ở nơi ở theo `users`); `lat` / `lng` cho phép NULL vì không phải lúc
    # nào cũng có toạ độ.
    address: Mapped[str] = mapped_column(String(300), default="")
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    items: Mapped[list] = mapped_column(JSON, default=list)  # [{name, category_code, qty, media_id}]
    # Khối lượng lưu thành KHOẢNG (ADR-0003): vision ước lượng kg từ ảnh sai
    # vài lần là bình thường, nên ngưỡng HITL so với ``weight_max_kg`` —
    # sai số phải nghiêng về phía cần người duyệt.
    weight_min_kg: Mapped[float] = mapped_column(Float, default=0.0)
    weight_max_kg: Mapped[float] = mapped_column(Float, default=0.0)
    # Giữ lại để tương thích code cũ; bằng trung điểm của khoảng.
    est_weight_kg: Mapped[float] = mapped_column(Float, default=0.0)
    preferred_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    preferred_window: Mapped[str] = mapped_column(String(30), default="")
    note: Mapped[str] = mapped_column(Text, default="")

    requires_hitl: Mapped[bool] = mapped_column(default=False, index=True)
    # Các ngưỡng đã kích hoạt: [{rule, value, threshold, label_vi}] — màn duyệt
    # BẮT BUỘC hiển thị khối này, hàng đợi không nói lý do là hàng đợi vô nghĩa.
    threshold_hit: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default=CHO_DUYET, index=True)
    # pending | approved | rejected | scheduled | done | cancelled
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reject_reason: Mapped[str] = mapped_column(String(80), default="")
    review_note: Mapped[str] = mapped_column(Text, default="")

    # Khối lượng THẬT do đội vệ sinh cân khi thu — điểm chỉ được trao từ con số
    # này, không bao giờ từ ước lượng của AI. Xem pickup_flow.xac_nhan_khoi_luong.
    weight_confirmed_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Lý do rơi vào trạng thái tranh chấp, tiếng Việt, ghi tại chỗ xác nhận.
    dispute_reason: Mapped[str] = mapped_column(String(160), default="")

    is_seed: Mapped[bool] = mapped_column(default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class PickupEvent(Base):
    """Một mốc trên timeline của yêu cầu thu gom (spec 4.8).

    Timeline là nơi HITL hiện ra với người dùng cuối, nên phải ghi thành bản
    ghi thật chứ không dựng lại từ trạng thái hiện tại.
    """

    __tablename__ = "pickup_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("pickup_requests.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))  # created | threshold | reviewed | routed | done | cancelled
    label_vi: Mapped[str] = mapped_column(String(200))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class PickupRoute(Base):
    """Một chuyến thu gom do agent gộp lịch đề xuất, người duyệt mới chốt."""

    __tablename__ = "pickup_routes"

    id: Mapped[int] = mapped_column(primary_key=True)
    service_date: Mapped[date] = mapped_column(Date, index=True)
    window: Mapped[str] = mapped_column(String(30), default="")
    team_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="proposed", index=True)
    # proposed | approved | in_progress | done
    total_weight_kg: Mapped[float] = mapped_column(Float, default=0.0)
    est_distance_km: Mapped[float] = mapped_column(Float, default=0.0)
    # Khối "Vì sao gộp thế này" (spec 4.12) — quan trọng bằng chính cái tuyến:
    # {criteria[], excluded[], baseline_km, saved_km, capacity_kg}.
    reasoning: Mapped[dict] = mapped_column(JSON, default=dict)
    # Bản AI đề xuất ban đầu, giữ nguyên để hiện diff khi người duyệt sửa tay.
    proposed_stop_order: Mapped[list] = mapped_column(JSON, default=list)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    is_seed: Mapped[bool] = mapped_column(default=False, index=True)
    # Gói P72 — phân biệt chuyến tự tạo (agent gộp lịch) với chuyến người tạo thủ
    # công. Giá trị: "thu_cong" (mặc định) | "tu_dong".
    nguon_tao: Mapped[str] = mapped_column(String(20), default="thu_cong", index=True)
    # Gói P73 — ai xác nhận chuyến xong. NULL = chưa ai xác nhận.
    xac_nhan_boi: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    # Gói P73 — thời điểm xác nhận chuyến xong.
    xac_nhan_luc: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    stops: Mapped[list[RouteStop]] = relationship(back_populates="route", cascade="all, delete-orphan")


# Hai loại điểm dừng trong cùng một chuyến. Xe chạy một vòng làm cả hai việc:
# ghé nhà cư dân lấy đồ cồng kềnh, và ghé thùng thông minh đang báo đầy.
STOP_KIND_YEU_CAU = "yeu_cau"
STOP_KIND_THUNG = "thung"
STOP_KINDS = frozenset({STOP_KIND_YEU_CAU, STOP_KIND_THUNG})


class RouteStop(Base):
    """Một điểm dừng trong chuyến thu gom.

    ``stop_kind`` quyết định khoá ngoại nào được điền:

    * ``yeu_cau`` — một yêu cầu thu gom của cư dân, dùng ``request_id``.
    * ``thung`` — một thùng thông minh đang báo cần gom, dùng ``bin_id``.

    Đúng một trong hai khoá được điền, khoá còn lại để ``None``. Ràng buộc đó
    kiểm ở tầng nghiệp vụ chứ không đặt CHECK constraint, để bảng còn tạo được
    y hệt nhau trên SQLite (dev) và PostgreSQL (deploy) khi dự án chưa dùng
    Alembic.
    """

    __tablename__ = "route_stops"

    id: Mapped[int] = mapped_column(primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("pickup_routes.id"), index=True)
    stop_kind: Mapped[str] = mapped_column(String(12), default=STOP_KIND_YEU_CAU, index=True)
    # Cho NULL vì điểm dừng loại "thung" không có yêu cầu nào đứng sau nó.
    request_id: Mapped[int | None] = mapped_column(ForeignKey("pickup_requests.id"), nullable=True, index=True)
    bin_id: Mapped[int | None] = mapped_column(ForeignKey("bins.id"), nullable=True, index=True)
    seq: Mapped[int] = mapped_column(default=0)
    done_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Đội vệ sinh báo phát sinh tại điểm dừng (spec 4.9).
    issue: Mapped[str] = mapped_column(String(80), default="")
    issue_note: Mapped[str] = mapped_column(Text, default="")
    actual_weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)

    route: Mapped[PickupRoute] = relationship(back_populates="stops")


class GPSLog(Base):
    """Bản ghi toạ độ GPS thu thập từ phương tiện thu gom khi đang chạy tuyến."""

    __tablename__ = "gps_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("pickup_routes.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    snapped_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    snapped_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed_mps: Mapped[float | None] = mapped_column(Float, nullable=True)
    heading: Mapped[float | None] = mapped_column(Float, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    route: Mapped[PickupRoute] = relationship()


class SuCoThuGom(Base):
    """Sự cố thu gom do người thu gom báo lên, ĐVTG duyệt (dùng ở P73).

    Người thu gom gặp rác phân loại sai, thùng đã đầy, hoặc chủ nhà không tiếp
    nhận thì báo lên; ĐVTG xem xét và xử lý (đã xử lý / từ chối).
    """

    __tablename__ = "su_co_thu_gom"

    id: Mapped[int] = mapped_column(primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("pickup_routes.id"), index=True)
    # Cho NULL vì sự cố có thể báo ở mức chuyến, chưa chỉ đích danh điểm dừng.
    stop_id: Mapped[int | None] = mapped_column(ForeignKey("route_stops.id"), nullable=True)
    nguoi_bao_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # phan_loai_sai | thung_day | khong_tiep_can | khac
    loai: Mapped[str] = mapped_column(String(40), default="khac", index=True)
    mo_ta: Mapped[str] = mapped_column(Text, default="")
    # Ảnh minh chứng, NULL nếu báo không có ảnh.
    anh_media_id: Mapped[int | None] = mapped_column(ForeignKey("media.id"), nullable=True)
    # cho_xu_ly | da_xu_ly | tu_choi
    trang_thai: Mapped[str] = mapped_column(String(20), default="cho_xu_ly", index=True)
    nguoi_xu_ly_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    ghi_chu_xu_ly: Mapped[str] = mapped_column(Text, default="")
    xu_ly_luc: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
