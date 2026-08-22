"""Điểm nhận thức và nhiệm vụ — API cho cư dân (P79).

Router chỉ lo HTTP; mọi luật nằm ở :mod:`src.services.diem_nhan_thuc`. Cả ba
endpoint đều bắt đăng nhập (`CurrentUser`) và chỉ cho người dùng xem/tác động
**của chính mình** — không có tham số ``user_id``. Điểm nhận thức tách bạch:
không bao giờ chạm điểm có giá trị / sổ cái điểm thưởng.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import desc, select

from src.api.deps import CurrentUser, DbSession
from src.db.models import DiemNhanThucLog
from src.services import diem_nhan_thuc

router = APIRouter(prefix="/diem", tags=["diem"])


@router.get("/nhan-thuc")
def xem_diem_nhan_thuc(session: DbSession, user: CurrentUser) -> dict:
    """Tổng điểm nhận thức của chính mình + 20 dòng sổ cái gần nhất."""
    hom_nay = datetime.now(UTC).date()
    gan_day = session.scalars(
        select(DiemNhanThucLog)
        .where(DiemNhanThucLog.user_id == user.id)
        .order_by(desc(DiemNhanThucLog.created_at), desc(DiemNhanThucLog.id))
        .limit(20)
    ).all()
    return {
        "tong_diem_nhan_thuc": diem_nhan_thuc.tong_diem_nhan_thuc(session, user_id=user.id),
        "hom_nay": hom_nay.isoformat(),
        "gan_day": [
            {
                "nguon": d.nguon,
                "diem": d.diem,
                "ref_bang": d.ref_bang,
                "ref_id": d.ref_id,
                "ngay": d.ngay.isoformat(),
                "ghi_chu": d.ghi_chu,
                "created_at": d.created_at.isoformat(),
            }
            for d in gan_day
        ],
    }


@router.get("/nhiem-vu")
def xem_nhiem_vu(session: DbSession, user: CurrentUser) -> dict:
    """Danh sách nhiệm vụ + tiến độ hiện tại + đã nhận hay chưa (kỳ hôm nay)."""
    hom_nay = datetime.now(UTC).date()
    return {
        "ngay": hom_nay.isoformat(),
        "items": diem_nhan_thuc.danh_sach_nhiem_vu(session, user=user, ngay=hom_nay),
    }


@router.post("/nhiem-vu/kiem")
def kiem_nhiem_vu(session: DbSession, user: CurrentUser) -> dict:
    """Chạy lại kiểm tra nhiệm vụ cho chính mình — đủ điều kiện thì trao điểm."""
    hom_nay = datetime.now(UTC).date()
    da_xong = diem_nhan_thuc.kiem_va_trao_nhiem_vu(session, user=user, ngay=hom_nay)
    return {
        "ngay": hom_nay.isoformat(),
        "da_hoan_thanh": da_xong,
        "tong_diem_nhan_thuc": diem_nhan_thuc.tong_diem_nhan_thuc(session, user_id=user.id),
    }
