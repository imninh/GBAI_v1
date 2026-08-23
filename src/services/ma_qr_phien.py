"""Mã QR thay đổi mỗi phiên — chống làm giả, mã dùng một lần.

Luồng:

1. Thiết bị xin mã → ``sinh_ma`` trả mã mới, vô hiệu mã cũ chưa dùng.
2. Người dùng quét QR → mở link web → đăng nhập → ``doi_ma_lay_phien``.
3. ``don_ma_het_han`` chạy nền dọn mã quá hạn.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config import get_settings
from src.db.models import Bin, MaQrThung, PhienThung, User
from src.services import phien_thung

THOI_HAN_MA_GIAY = 120


def sinh_ma(session: Session, *, bin_code: str) -> MaQrThung:
    """Sinh mã QR mới cho thùng ``bin_code``.

    - Không tìm thấy thùng → ``ValueError``.
    - Mã cũ chưa dùng của thùng đó → bị vô hiệu (``da_dung=True``).
    - Mã mới hết hạn sau ``THOI_HAN_MA_GIAY`` giây.
    """
    thung = session.scalar(select(Bin).where(Bin.code == bin_code))
    if thung is None:
        raise ValueError(f"Không tìm thấy thùng có mã '{bin_code}'.")

    # Vô hiệu mọi mã cũ chưa dùng của thùng này
    now = datetime.now(UTC)
    ma_cu = session.scalars(
        select(MaQrThung).where(
            MaQrThung.bin_id == thung.id,
            MaQrThung.da_dung.is_(False),
        )
    ).all()
    for m in ma_cu:
        m.da_dung = True
        m.da_dung_luc = now

    ma_moi = MaQrThung(
        bin_id=thung.id,
        ma=secrets.token_urlsafe(24),
        het_han_luc=now + timedelta(seconds=THOI_HAN_MA_GIAY),
    )
    session.add(ma_moi)
    session.flush()
    return ma_moi


def duong_link(ma: str) -> str:
    """Đường link web mà mã QR chứa.

    Dùng query string trên đường gốc ``/`` vì web là bản xuất tĩnh, chỉ có ba
    đường thật (``/``, ``/tai-app/``, ``/dieu-phoi/`` — ARCHITECTURE.md mục 18.1).
    """
    goc = get_settings().web_app_base_url.rstrip("/")
    return f"{goc}/?ma={ma}"


def doi_ma_lay_phien(session: Session, *, user: User, ma: str) -> PhienThung:
    """Đổi mã QR lấy phiên bỏ rác.

    Kiểm theo đúng thứ tự, ném lỗi khác nhau cho từng ca:

    1. Không tìm thấy mã → ``ValueError("Mã QR không hợp lệ.")``
    2. Mã đã dùng   → ``ValueError("Mã QR đã được sử dụng.")``
    3. Mã hết hạn    → ``ValueError("Mã QR đã hết hạn.")``

    Qua hết thì mở phiên, đánh dấu mã đã dùng.
    """
    ma_qr = session.scalar(select(MaQrThung).where(MaQrThung.ma == ma))

    if ma_qr is None:
        raise ValueError("Mã QR không hợp lệ.")

    if ma_qr.da_dung:
        raise ValueError("Mã QR đã được sử dụng.")

    now = datetime.now(UTC)
    if ma_qr.het_han_luc < now:
        raise ValueError("Mã QR đã hết hạn.")

    # Lấy mã thùng từ bin_id
    thung = session.get(Bin, ma_qr.bin_id)
    if thung is None:
        raise ValueError("Mã QR không hợp lệ.")

    phien = phien_thung.mo_phien(session, user, thung.code)

    ma_qr.da_dung = True
    ma_qr.da_dung_luc = now
    ma_qr.phien_id = phien.id
    session.flush()
    return phien


def don_ma_het_han(session: Session) -> int:
    """Đánh dấu mọi mã quá hạn là đã dùng. Trả số dòng đã dọn.

    Không xoá dòng nào — giữ lại để tra vết.
    """
    now = datetime.now(UTC)
    ma_het_han = session.scalars(
        select(MaQrThung).where(
            MaQrThung.da_dung.is_(False),
            MaQrThung.het_han_luc < now,
        )
    ).all()
    for m in ma_het_han:
        m.da_dung = True
        m.da_dung_luc = now
    session.flush()
    return len(ma_het_han)
