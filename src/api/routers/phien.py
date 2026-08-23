"""Phiên bỏ rác tại thùng — API cho cư dân (P63).

Router chỉ lo HTTP; mọi luật nằm ở :mod:`src.services.phien_thung`.

Chỉ chủ phiên xem và đóng được phiên của mình — người khác gọi → **404**, không
phải 403 (403 xác nhận mã phiên đó có thật).
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from src.api.deps import CurrentUser, DbSession
from src.api.errors import bad_request, not_found
from src.db.models import Bin, PhienThung, User
from src.services import phien_thung

router = APIRouter(prefix="/phien", tags=["phien"])


class BatDauPayload(BaseModel):
    """Body mở phiên — chỉ cần mã thùng quét từ QR."""

    bin_code: str = Field(min_length=1, max_length=40)


def _khuon(phien: PhienThung) -> dict:
    return {
        "ma_phien": phien.ma_phien,
        "trang_thai": phien.trang_thai,
        "so_vat": phien.so_vat,
        "diem_nhan_thuc": phien.diem_nhan_thuc,
        "bat_dau": phien.bat_dau.isoformat(),
        "ket_thuc": phien.ket_thuc.isoformat() if phien.ket_thuc else None,
    }


@router.post("/bat-dau")
def bat_dau(payload: BatDauPayload, session: DbSession, user: CurrentUser) -> dict:
    """Mở phiên bỏ rác tại thùng. Trả phiên đang mở (cũ nếu đã có của chính mình)."""
    try:
        phien = phien_thung.mo_phien(session, user, payload.bin_code)
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
