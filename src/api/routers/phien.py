"""Phiên bỏ rác tại thùng — API cho cư dân (P63).

Router chỉ lo HTTP; mọi luật nằm ở :mod:`src.services.phien_thung`.

Chỉ chủ phiên xem và đóng được phiên của mình — người khác gọi → **404**, không
phải 403 (403 xác nhận mã phiên đó có thật).
"""

from __future__ import annotations

from datetime import UTC, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from src.api.deps import CurrentUser, DbSession
from src.api.errors import bad_request, not_found
from src.config import get_settings
from src.db.models import Bin, PhienThung, User
from src.services import ma_qr_phien, phien_thung
from src.services.device_auth import DeviceAuthError, authenticate

router = APIRouter(prefix="/phien", tags=["phien"])


class BatDauPayload(BaseModel):
    """Body mở phiên — chỉ cần mã thùng quét từ QR."""

    bin_code: str = Field(min_length=1, max_length=40)


def _khuon(phien: PhienThung) -> dict:
    # Mốc hết hạn của phiên = bat_dau + 10 phút (logic server, xem
    # THOI_GIAN_TOI_DA_GIAY trong src.services.phien_thung). Tính ở server, trả
    # timestamp UTC rõ ràng để frontend đếm ngược — KHÔNG tự bịa mốc phía client.
    bat_dau = phien.bat_dau
    if bat_dau.tzinfo is None:
        bat_dau = bat_dau.replace(tzinfo=UTC)
    return {
        "ma_phien": phien.ma_phien,
        "trang_thai": phien.trang_thai,
        "so_vat": phien.so_vat,
        "diem_nhan_thuc": phien.diem_nhan_thuc,
        "bat_dau": phien.bat_dau.isoformat(),
        "ket_thuc": phien.ket_thuc.isoformat() if phien.ket_thuc else None,
        "het_han_luc": (bat_dau + timedelta(seconds=phien_thung.THOI_GIAN_TOI_DA_GIAY)).isoformat(),
    }


@router.post("/bat-dau")
def bat_dau(payload: BatDauPayload, session: DbSession, user: CurrentUser) -> dict:
    """Mở phiên bỏ rác tại thùng. Trả phiên đang mở (cũ nếu đã có của chính mình)."""
    try:
        phien = phien_thung.mo_phien(session, user, payload.bin_code)
    except ValueError as exc:
        raise bad_request(str(exc), code="PHIEN-400") from exc
    return _khuon(phien)


async def _require_device_key(x_device_key: str | None = Header(default=None)) -> str:
    """FastAPI dependency: xác thực thiết bị IoT — chép đúng khuôn từ iot.py."""
    try:
        return authenticate(x_device_key)
    except DeviceAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


class MaQrRequest(BaseModel):
    """Thân yêu cầu xin mã QR — thiết bị gửi mã thùng."""

    bin_code: str = Field(min_length=1, max_length=40)


@router.post("/ma-qr")
def tao_ma_qr(
    payload: MaQrRequest,
    session: DbSession,
    device_id: str = Depends(_require_device_key),
) -> dict:
    """Thiết bị xin mã QR cho thùng. Trả ``{ma, url, het_han_luc}``."""
    dia_chi_web = get_settings().web_app_base_url.strip()
    if not dia_chi_web:
        raise HTTPException(
            status_code=503,
            detail="Chưa cấu hình địa chỉ ứng dụng web — mã QR không thể tạo lúc này.",
        )
    try:
        ma_qr = ma_qr_phien.sinh_ma(session, bin_code=payload.bin_code)
    except ValueError as exc:
        raise bad_request(str(exc), code="QR-400") from exc
    return {
        "ma": ma_qr.ma,
        "url": ma_qr_phien.duong_link(ma_qr.ma),
        "het_han_luc": ma_qr.het_han_luc.isoformat(),
    }


class BatDauBangMaPayload(BaseModel):
    """Thân yêu cầu mở phiên bằng mã QR."""

    ma: str = Field(min_length=1, max_length=128)


@router.post("/bat-dau-bang-ma")
def bat_dau_bang_ma(
    payload: BatDauBangMaPayload,
    session: DbSession,
    user: CurrentUser,
) -> dict:
    """Người dùng quét QR → mở phiên bằng mã. Trả đúng khuôn ``/phien/bat-dau``."""
    try:
        phien = ma_qr_phien.doi_ma_lay_phien(session, user=user, ma=payload.ma)
    except ValueError as exc:
        raise bad_request(str(exc), code="PHIEN-400") from exc
    return _khuon(phien)


def _tra_phien(session: DbSession, ma_phien: str, user: CurrentUser) -> PhienThung:
    phien = session.scalar(select(PhienThung).where(PhienThung.ma_phien == ma_phien))
    if phien is None or phien.user_id != user.id:
        raise not_found("phiên này")
    return phien


@router.get("/{ma_phien}")
def xem_phien(ma_phien: str, session: DbSession, user: CurrentUser) -> dict:
    """Trạng thái phiên, số vật, điểm nhận thức tạm tính."""
    return _khuon(_tra_phien(session, ma_phien, user))


@router.post("/{ma_phien}/dong")
def dong_phien(ma_phien: str, session: DbSession, user: CurrentUser) -> dict:
    """Chốt phiên: tính điểm nhận thức, sinh thông báo trong app."""
    phien = _tra_phien(session, ma_phien, user)
    try:
        da_dong = phien_thung.dong_phien(session, phien)
    except ValueError as exc:
        raise bad_request(str(exc), code="PHIEN-400") from exc
    return _khuon(da_dong)


@router.get("/thung/{bin_code}/hien-tai")
def phien_hien_tai_cua_thung(bin_code: str, session: DbSession) -> dict:
    """Kiểm tra phiên đang mở của thùng (dành cho Kiosk/IoT polling)."""
    thung = session.scalar(select(Bin).where(Bin.code == bin_code))
    if thung is None:
        return {"co_phien": False, "ma_phien": None, "bin_code": bin_code}

    phien = phien_thung.phien_dang_mo_cua_thung(session, thung.id)
    if phien is None:
        return {"co_phien": False, "ma_phien": None, "bin_code": bin_code}

    u = session.get(User, phien.user_id)
    return {
        "co_phien": True,
        "ma_phien": phien.ma_phien,
        "bin_code": bin_code,
        "so_vat": phien.so_vat,
        "diem_nhan_thuc": phien.diem_nhan_thuc,
        "user_id": phien.user_id,
        "user_name": u.full_name if u else f"USER #{phien.user_id}",
    }
