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

from src.api.deps import DbSession, require
from src.api.errors import ApiError, bad_request, not_found
from src.config import get_settings
from src.db.models import Bin, User, utcnow
from src.services import bins, khoa_thiet_bi
from src.services.auth import write_audit

router = APIRouter(tags=["bins"])


class ReadingPayload(BaseModel):
    """Body của một lần thùng báo về mức rác và mức pin."""

    fill_percent: float
    battery_percent: float
    source: str


NGUON_HOP_LE = frozenset({"device", "simulator", "manual"})


class AssignPayload(BaseModel):
    """Body của lệnh giao thùng. ``cleaner_id = null`` nghĩa là bỏ gán."""

    cleaner_id: int | None = None


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


@router.post("/bins/{code}/readings")
def nhan_reading(
    code: str,
    payload: ReadingPayload,
    session: DbSession,
    x_device_key: Annotated[str | None, Header(alias="X-Device-Key")] = None,
) -> dict:
    """Thiết bị (hoặc bộ mô phỏng thay thế) báo mức rác và pin của một thùng.

    Endpoint này KHÔNG cần JWT người dùng — thiết bị không đăng nhập được, nó
    xác thực bằng ``X-Device-Key``.
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
