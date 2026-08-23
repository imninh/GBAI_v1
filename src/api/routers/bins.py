"""Thùng thu gom thông minh — phía đọc cho bản đồ vận hành.

Đơn vị thu gom mở màn hình xem thùng nào ``can_gom`` (đầy, cần ghé), thùng nào
``mat_ket_noi`` (lần báo cuối đã lâu) và ``het_pin``. Trạng thái tính từ
:mod:`src.services.bins` — mọi quy tắc trạng thái chỉ có một nơi duy nhất,
router chỉ nối dữ liệu sang HTTP chứ không lặp lại logic.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.deps import DbSession, require
from src.api.errors import ApiError, bad_request, not_found
from src.config import get_settings
from src.db.models import Bin, User, utcnow
from src.services import bins, device_auth, khoa_thiet_bi
from src.services.auth import write_audit

router = APIRouter(tags=["bins"])


class ReadingPayload(BaseModel):
    """Body của một lần thùng báo về mức rác và mức pin."""

    fill_percent: float
    battery_percent: float = 100.0
    source: str = "device"
    device_id: str | None = None
    is_full: bool | None = None
    uptime_s: int = 0


NGUON_HOP_LE = frozenset({"device", "simulator", "manual"})


class AssignPayload(BaseModel):
    """Body của lệnh giao thùng. ``cleaner_id = null`` nghĩa là bỏ gán."""

    cleaner_id: int | None = None


class TaoThungPayload(BaseModel):
    """Body tạo thùng mới (gói P31). Mã và tên bắt buộc, toạ độ tuỳ chọn.

    Đơn vị sở hữu của thùng không nhận từ client — lấy theo người tạo, không để
    ai tạo thùng cho đơn vị khác.
    """

    code: str
    name: str
    address: str = ""
    lat: float | None = None
    lng: float | None = None
    category_codes: list[str] = []
    capacity_liters: float = 0.0
    building_id: int | None = None


class CapNhatThungPayload(BaseModel):
    """Body sửa thùng (gói P31) — mọi trường tuỳ chọn, không truyền là không đổi.

    Đọc bằng ``model_dump(exclude_unset=True)`` để phân biệt "không gửi" với "gửi
    null" (ví dụ gửi ``lat: null`` là cố ý xoá toạ độ).
    """

    name: str | None = None
    address: str | None = None
    lat: float | None = None
    lng: float | None = None
    category_codes: list[str] | None = None
    capacity_liters: float | None = None


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Bản sao JSON-safe của một thùng, đúng khối mà ``/bins`` trả về."""
    return {
        "id": row["id"],
        "code": row["code"],
        "name": row["name"],
        "building_id": row["building_id"],
        "address": row["address"],
        "category_codes": row["category_codes"],
        "lat": row["lat"],
        "lng": row["lng"],
        "fill_percent": row["fill_percent"],
        "battery_percent": row["battery_percent"],
        # Ai đang được giao thùng này. `None` = chưa gán ai.
        "assigned_cleaner_id": row["assigned_cleaner_id"],
        "last_seen_at": row["last_seen_at"].isoformat() if row["last_seen_at"] else None,
        "status": row["status"],
    }


def _phan_hoi_thung(session: Session, thung: Bin, readings_limit: int = 20) -> dict[str, Any]:
    """Khuôn chi tiết thùng đúng ``GET /bins/{code}`` — một hình dạng duy nhất
    cho mọi endpoint chạm thùng, không đẻ ra dạng thứ hai cho cùng một thực thể.
    """
    now = utcnow()
    phan_hoi = _serialize_row(
        {
            "id": thung.id,
            "code": thung.code,
            "name": thung.name,
            "building_id": thung.building_id,
            "address": thung.address,
            "category_codes": thung.category_codes or [],
            "lat": thung.lat,
            "lng": thung.lng,
            "fill_percent": thung.fill_percent,
            "battery_percent": thung.battery_percent,
            "last_seen_at": thung.last_seen_at,
            "assigned_cleaner_id": thung.assigned_cleaner_id,
            "status": bins.trang_thai_thung(thung, now),
        }
    )
    phan_hoi["readings"] = [
        {**dong, "created_at": dong["created_at"].isoformat() if dong["created_at"] else None}
        for dong in bins.lich_su_readings(session, thung.id, limit=readings_limit)
    ]
    return phan_hoi


@router.get("/bins")
def list_bins(
    session: DbSession,
    user: Annotated[User, Depends(require("view_bins"))],
    only_needs_collection: bool = False,
) -> dict:
    """Danh sách thùng kèm trạng thái, lọc được theo thùng cần gom.

    Nhân viên vệ sinh chỉ thấy thùng được giao cho mình; ban quản lý thấy tất
    cả, kể cả thùng chưa giao ai. Xem ``bins.loc_theo_nguoi_xem``.
    """
    now = utcnow()
    rows = bins.danh_sach_thung(
        session,
        now,
        chi_can_gom=only_needs_collection,
        cua_nhan_vien=bins.loc_theo_nguoi_xem(user),
        cua_to_chuc=bins.to_chuc_cua_nguoi_xem(user),
    )
    return {"items": [_serialize_row(r) for r in rows]}


# ⚠️ PHẢI đặt trước /bins/{code}: FastAPI chọn endpoint theo thứ tự khai báo.
# Nếu {code} được khai trước, "stats" sẽ bị coi là một mã thùng, mọi request tới
# /bins/stats đều rơi vào nhánh 404 và bốn con số trên dashboard biến mất.
@router.get("/bins/stats")
def bin_stats(
    session: DbSession,
    user: Annotated[User, Depends(require("view_bins"))],
) -> dict:
    """Bốn con số cho bốn thẻ trên dashboard điều phối.

    Đếm đúng tập thùng mà người đang đăng nhập nhìn thấy ở ``GET /bins``.
    """
    return bins.thong_ke_thung(
        session,
        utcnow(),
        cua_nhan_vien=bins.loc_theo_nguoi_xem(user),
        cua_to_chuc=bins.to_chuc_cua_nguoi_xem(user),
    )


@router.get("/bins/diem-gui")
def diem_gui(
    session: DbSession,
    user: Annotated[User, Depends(require("view_diem_gui"))],
) -> dict:
    """Điểm gửi rác cho app cư dân — bản thu gọn, không kèm dữ liệu vận hành."""
    return {"items": bins.diem_gui_cho_cu_dan(session, utcnow())}


@router.get("/bins/nhan-vien")
def danh_sach_nhan_vien(
    session: DbSession,
    user: Annotated[User, Depends(require("assign_bin"))],
) -> dict:
    """Nhân viên vệ sinh kèm số thùng đang được giao — cho màn giao thùng.

    Quyền ``assign_bin`` chứ không phải ``view_bins``: chỉ người **giao được**
    thùng mới cần danh sách người nhận. Nhân viên không có việc gì phải biết
    đồng nghiệp đang giữ bao nhiêu thùng.
    """
    return {
        "items": bins.danh_sach_nhan_vien(session, cua_to_chuc=bins.to_chuc_cua_nguoi_xem(user))
    }


@router.get("/bins/{code}")
def get_bin(
    code: str,
    session: DbSession,
    user: Annotated[User, Depends(require("view_bins"))],
    readings_limit: int = 20,
) -> dict:
    """Chi tiết một thùng cho bản đồ vận hành."""
    thung = session.scalar(select(Bin).where(Bin.code == code))
    # Thùng không tồn tại và thùng không thuộc về mình trả về **cùng một lỗi**.
    # Trả 403 cho vế thứ hai là xác nhận "mã này có thật" — đủ để dò ra toàn bộ
    # danh sách mã thùng bằng cách thử lần lượt.
    if thung is None or not bins.xem_duoc_thung(
        thung, bins.loc_theo_nguoi_xem(user), bins.to_chuc_cua_nguoi_xem(user)
    ):
        raise not_found(f"thùng có mã '{code}'")
    return _phan_hoi_thung(session, thung, readings_limit=readings_limit)


@router.post("/bins/{code}/readings")
def nhan_reading(
    code: str,
    payload: ReadingPayload,
    session: DbSession,
    x_device_key: Annotated[str | None, Header(alias="X-Device-Key")] = None,
    x_device_timestamp: Annotated[str | None, Header(alias="X-Device-Timestamp")] = None,
    x_device_signature: Annotated[str | None, Header(alias="X-Device-Signature")] = None,
) -> Any:
    """Thiết bị (hoặc bộ mô phỏng thay thế) báo mức rác và pin của một thùng.

    Endpoint này KHÔNG cần JWT người dùng — thiết bị không đăng nhập được, nó
    xác thực bằng ``X-Device-Key``.

    Gói P58 gộp ngã ba xác thực về MỘT cửa: trước đây firmware (có ``device_id``
    trong thân) rẽ sang ``device_auth`` rồi ghi vào kho trong bộ nhớ, còn đường
    không có ``device_id`` mới chạy ``khoa_thiet_bi`` + CSDL. Firmware ESP32 luôn
    gửi ``device_id`` nên mọi thùng thật rơi vào nhánh chết (bảng khoá rỗng →
    401, số liệu không vào CSDL). Giờ chỉ còn MỘT đường: tra thùng theo ``code``
    → ``khoa_thiet_bi.kiem_khoa`` → ``bins.ghi_nhan_reading`` xuống CSDL thật.

    ``device_id`` trong thân vẫn được chấp nhận (firmware vẫn gửi nguyên vẹn),
    nhưng khoá ràng theo THÙNG (qua ``code`` trên đường dẫn): một khoá hợp lệ
    của thùng A không mở được thùng B, vì mỗi thùng có ``device_key_hash`` riêng
    (hoặc rơi về khoá chung). Xem ``khoa_thiet_bi.kiem_khoa``.
    """
    settings = get_settings()

    khoa_nhan = (x_device_key or "").strip()

    if payload.source not in NGUON_HOP_LE:
        raise bad_request(
            f"Nguồn '{payload.source}' không hợp lệ — phải là device, simulator hoặc manual.",
            code="BIN-400",
        )

    thung = session.scalar(select(Bin).where(Bin.code == code))
    if thung is None:
        raise not_found(f"thùng có mã '{code}'")

    # FAIL CLOSED — chặn khi (khoá chung chưa cấu hình) MÀ (thùng cũng chưa có
    # khoá riêng). Thùng đã có khoá riêng thì khoá chung không liên quan gì tới
    # nó nữa — chặn nốt cả nhóm đó là một thùng đang hoạt động bị bóp nghẹt giữa
    # chừng dù khoá của nó vẫn đúng. Endpoint này ghi các con số mà quyết định
    # điều phối dựa vào — không bao giờ "ai cũng vào được".
    if not settings.bin_device_key and not thung.device_key_hash:
        raise ApiError(
            503,
            "BIN-KEY-503",
            "Chưa cấu hình khoá thiết bị (BIN_DEVICE_KEY) — vui lòng đặt trong .env trước khi bật chức năng ghi nhận.",
        )

    # Kiểm khoá SAU khi tra được thùng, vì mỗi thùng có thể có khoá riêng. Thùng
    # chưa cấp khoá riêng thì rơi về khoá chung — xem `khoa_thiet_bi.kiem_khoa`.
    if not khoa_thiet_bi.kiem_khoa(thung, khoa_nhan, settings.bin_device_key):
        raise ApiError(401, "BIN-KEY-401", "Khoá thiết bị không hợp lệ hoặc bị thiếu.")

    # Chống phát lại chỉ xét KHI khoá đã xác thực thành công — khoá sai thì 401
    # ngay như cũ. Khoá HMAC là CHUỖI KHOÁ THÔ vừa mở được thùng (khoá chung hay
    # khoá riêng đều như vậy), không phải bản băm trong CSDL: server không tính
    # lại HMAC từ băm được, nhưng khoá thô thiết bị vừa gửi thì đang cầm trong
    # tay. Cờ tắt (mặc định) ⇒ bỏ qua hẳn, request kiểu cũ chạy như trước.
    if settings.iot_chong_phat_lai and not device_auth.kiem_chong_phat_lai(
        payload.device_id or code,
        khoa_nhan,
        x_device_timestamp,
        x_device_signature,
    ):
        raise ApiError(401, "BIN-KEY-401", "Khoá thiết bị không hợp lệ hoặc bị thiếu.")

    now = utcnow()
    try:
        bins.ghi_nhan_reading(session, thung, payload.fill_percent, payload.battery_percent, payload.source, now)
    except ValueError as exc:
        raise bad_request(str(exc), code="BIN-400") from exc

    # Trạng thái tính NGAY trên đối tượng vừa ghi (chưa đọc lại từ CSDL) — đúng
    # ca mà phép chuẩn hoá aware/naive trong bins.trang_thai_thung được viết ra.
    return _serialize_row(
        {
            "id": thung.id,
            "code": thung.code,
            "name": thung.name,
            "building_id": thung.building_id,
            "address": thung.address,
            "category_codes": thung.category_codes or [],
            "lat": thung.lat,
            "lng": thung.lng,
            "fill_percent": thung.fill_percent,
            "battery_percent": thung.battery_percent,
            "last_seen_at": thung.last_seen_at,
            "assigned_cleaner_id": thung.assigned_cleaner_id,
            "status": bins.trang_thai_thung(thung, now),
        }
    )


@router.get("/bins/{code}/readings")
def list_bin_readings(code: str, session: DbSession, limit: int = 50) -> list[dict]:
    """Lịch sử báo về của một thùng, mới trước cũ sau.

    Gói P61/P58: POST giờ ghi xuống CSDL thật (bảng ``bin_readings``) qua
    ``bins.ghi_nhan_reading``, nên GET phải đọc từ CSDL — đọc kho in-memory cũ là
    trả rỗng vô nghĩa ngoài đời. Dùng đúng hàm ``_phan_hoi_thung`` đang dùng
    (``bins.lich_su_readings``); giữ nguyên đường dẫn và tham số ``limit``.

    ⚠️ Khuôn trả về đổi từ ``schemas.BinReading`` (yêu cầu device_id/is_full/
    uptime_s/reading_id mà bảng ``bin_readings`` KHÔNG có) sang đúng khối
    ``lich_su_readings`` — chính là khuôn ``_phan_hoi_thung`` trả cho frontend
    (``fill_percent/battery_percent/source/created_at``). Trả khuôn cũ buộc phải
    bịa 4 trường không tồn tại trong CSDL.
    """
    thung = session.scalar(select(Bin).where(Bin.code == code))
    if thung is None:
        return []
    return bins.lich_su_readings(session, thung.id, limit=limit)



@router.patch("/bins/{code}/nhan-vien")
def gan_nhan_vien(
    code: str,
    payload: AssignPayload,
    session: DbSession,
    user: Annotated[User, Depends(require("assign_bin"))],
) -> dict:
    """Ban quản lý giao một thùng cho nhân viên vệ sinh, hoặc bỏ gán.

    Đường dẫn có hậu tố riêng ``/nhan-vien`` nên không đụng ``/bins/{code}``, và
    đây là PATCH trong khi các endpoint kia là GET — không rơi vào cái bẫy thứ
    tự khai báo đã ghi ở đầu file.
    """
    thung = session.scalar(select(Bin).where(Bin.code == code))
    if thung is None:
        raise not_found(f"thùng có mã '{code}'")

    nhan_vien: User | None = None
    if payload.cleaner_id is not None:
        nhan_vien = session.get(User, payload.cleaner_id)
        if nhan_vien is None:
            raise not_found(f"nhân viên có id {payload.cleaner_id}")

    # Chụp giá trị cũ TRƯỚC khi đổi — chụp sau là ghi vào nhật ký hai giá trị
    # giống hệt nhau, nhật ký thành vô dụng.
    truoc = thung.assigned_cleaner_id
    try:
        bins.gan_thung_cho_nhan_vien(session, thung, nhan_vien)
    except ValueError as exc:
        raise bad_request(str(exc), code="BIN-400") from exc

    write_audit(
        session,
        actor=user,
        action="assign_bin",
        entity="bin",
        entity_id=thung.code,
        detail={"truoc": truoc, "sau": thung.assigned_cleaner_id},
    )
    return {
        "code": thung.code,
        "assigned_cleaner_id": thung.assigned_cleaner_id,
        "assigned_cleaner_name": nhan_vien.full_name if nhan_vien is not None else "",
    }


# --- Gói P31: ban quản lý thêm / sửa / ngừng dùng thùng ------------------------
#
# Bốn route dưới đây đặt cuối file. Không route nào bị `/bins/{code}` nuốt: nó
# có đúng MỘT đoạn đường dẫn, còn `/bins/{code}/kich-hoat` và `/bins/{code}/readings`
# có HAI đoạn với hậu tố khác nhau — FastAPI khớp theo số đoạn, nên không có
# chuyện literal bị tham số hút về. `POST /bins` không tham số nên cũng vô hại.


@router.post("/bins", status_code=201)
def tao_bin(
    payload: TaoThungPayload,
    session: DbSession,
    user: Annotated[User, Depends(require("manage_bins"))],
) -> dict:
    """Ban quản lý tạo một thùng thu gom mới (gói P31)."""
    try:
        thung = bins.tao_thung(session, payload.model_dump(), user)
    except ValueError as exc:
        raise bad_request(str(exc), code="BIN-400") from exc
    return _phan_hoi_thung(session, thung)


@router.patch("/bins/{code}")
def sua_bin(
    code: str,
    payload: CapNhatThungPayload,
    session: DbSession,
    user: Annotated[User, Depends(require("manage_bins"))],
) -> dict:
    """Ban quản lý sửa các trường cho phép của một thùng.

    PATCH đúng nghĩa: trường không gửi thì không đổi. `code` và số đo thiết bị
    nằm ngoài danh sách trắng của `bins.sua_thung` nên không bao giờ chạm được.
    """
    thung = session.scalar(select(Bin).where(Bin.code == code))
    if thung is None:
        raise not_found(f"thùng có mã '{code}'")
    try:
        thung = bins.sua_thung(session, code, payload.model_dump(exclude_unset=True), user)
    except ValueError as exc:
        raise bad_request(str(exc), code="BIN-400") from exc
    return _phan_hoi_thung(session, thung)


@router.delete("/bins/{code}")
def ngung_dung_bin(
    code: str,
    session: DbSession,
    user: Annotated[User, Depends(require("manage_bins"))],
) -> dict:
    """Ban quản lý ngừng dùng một thùng — tắt hoạt động, GIỮ nguyên lịch sử.

    Là "ngừng dùng" chứ không phải "xoá": thùng ngừng dùng biến mất khỏi danh
    sách điều phối và điểm gửi của cư dân, nhưng hàng `bins` và toàn bộ
    `bin_readings` vẫn còn — xoá hàng là xoá luôn lịch sử mức rác/pin (cascade
    delete-orphan) và làm hỏng hồ sơ tuyến cũ còn tham chiếu `bin_id`.
    """
    thung = session.scalar(select(Bin).where(Bin.code == code))
    if thung is None:
        raise not_found(f"thùng có mã '{code}'")
    try:
        thung = bins.ngung_dung_thung(session, code, user)
    except ValueError as exc:
        raise bad_request(str(exc), code="BIN-400") from exc
    return _phan_hoi_thung(session, thung)


@router.post("/bins/{code}/kich-hoat")
def kich_hoat_bin(
    code: str,
    session: DbSession,
    user: Annotated[User, Depends(require("manage_bins"))],
) -> dict:
    """Ban quản lý đưa một thùng đã ngừng dùng trở lại hoạt động."""
    thung = session.scalar(select(Bin).where(Bin.code == code))
    if thung is None:
        raise not_found(f"thùng có mã '{code}'")
    try:
        thung = bins.kich_hoat_lai_thung(session, code, user)
    except ValueError as exc:
        raise bad_request(str(exc), code="BIN-400") from exc
    return _phan_hoi_thung(session, thung)
