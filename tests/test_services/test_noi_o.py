"""Nơi ở của cư dân — `noi_o_cua` là chỗ DUY NHẤT quyết định "người này ở đâu".

Gói P52 tách hai khái niệm đang bị nhập làm một: quan hệ hành chính
(``unit_id`` → toà) và toạ độ địa lý (cột riêng ``address``/``lat``/``lng``).
Thứ tự ưu tiên: toà thắng, rồi tới cột riêng của user, rồi tới rỗng.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from src.db.models import Building, Unit, User
from src.services.noi_o import co_noi_o, noi_o_cua


@pytest.fixture
def toa_va_can_ho(db_session: Session) -> tuple[Building, Unit]:
    toa = Building(
        code="NOI-O-1",
        name="Toà noi_o",
        address="123 Lý Thường Kiệt, Hoàn Kiếm, Hà Nội",
        lat=21.0271,
        lng=105.8519,
    )
    db_session.add(toa)
    db_session.flush()
    can_ho = Unit(building_id=toa.id, code="NOI-O-01")
    db_session.add(can_ho)
    db_session.flush()
    return toa, can_ho


def _cu_dan(db_session: Session, **kwargs) -> User:
    cu_dan = User(
        email=kwargs.pop("email", "cu-dan-noi-o@demo.vn"),
        full_name="Cư dân noi_o",
        role="resident",
        password_hash="x",
        **kwargs,
    )
    db_session.add(cu_dan)
    db_session.flush()
    return cu_dan


def test_co_can_ho_thi_tra_ngay_toa(db_session: Session, toa_va_can_ho: tuple[Building, Unit]) -> None:
    toa, can_ho = toa_va_can_ho
    cu_dan = _cu_dan(db_session, unit_id=can_ho.id)

    dia_chi, lat, lng = noi_o_cua(db_session, cu_dan)

    assert dia_chi == toa.address
    assert lat == toa.lat
    assert lng == toa.lng


def test_khong_can_ho_co_address_tra_cot_rieng(db_session: Session) -> None:
    cu_dan = _cu_dan(
        db_session,
        address="45 Hai Bà Trưng, Hoàn Kiếm, Hà Nội",
        lat=21.0199,
        lng=105.8528,
    )

    dia_chi, lat, lng = noi_o_cua(db_session, cu_dan)

    assert dia_chi == "45 Hai Bà Trưng, Hoàn Kiếm, Hà Nội"
    assert lat == 21.0199
    assert lng == 105.8528


def test_khong_co_gi_thi_tra_rong(db_session: Session) -> None:
    cu_dan = _cu_dan(db_session)

    assert noi_o_cua(db_session, cu_dan) == ("", None, None)


def test_co_ca_hai_thi_toa_thang(db_session: Session, toa_va_can_ho: tuple[Building, Unit]) -> None:
    """Có căn hộ VÀ có cột địa chỉ riêng → toà thắng (khẳng định thứ tự ưu tiên)."""
    toa, can_ho = toa_va_can_ho
    cu_dan = _cu_dan(
        db_session,
        unit_id=can_ho.id,
        address="Địa chỉ riêng không liên quan",
        lat=1.0,
        lng=2.0,
    )

    dia_chi, lat, lng = noi_o_cua(db_session, cu_dan)

    assert dia_chi == toa.address
    assert lat == toa.lat
    assert lng == toa.lng


def test_co_noi_o_dung_theo_noi_o_cua(db_session: Session, toa_va_can_ho: tuple[Building, Unit]) -> None:
    toa, can_ho = toa_va_can_ho
    assert co_noi_o(db_session, _cu_dan(db_session, email="a@noi-o.vn", unit_id=can_ho.id)) is True
    assert co_noi_o(db_session, _cu_dan(db_session, email="b@noi-o.vn", address="số 1 đường X")) is True
    assert co_noi_o(db_session, _cu_dan(db_session, email="c@noi-o.vn")) is False


def test_chi_toa_khong_can_ho_tra_toa(db_session: Session, toa_va_can_ho: tuple[Building, Unit]) -> None:
    """Gói worker 27/08: cư dân chỉ gắn toà (chưa gắn căn) vẫn trả toạ độ toà."""
    toa, _ = toa_va_can_ho
    cu_dan = _cu_dan(db_session, building_id=toa.id)

    dia_chi, lat, lng = noi_o_cua(db_session, cu_dan)

    assert dia_chi == toa.address
    assert lat == toa.lat
    assert lng == toa.lng


def test_chi_toa_van_thang_ca_address_rieng(db_session: Session, toa_va_can_ho: tuple[Building, Unit]) -> None:
    """Toà thắng cả khi user có cả cột địa chỉ riêng — khẳng định thứ tự ưu tiên."""
    toa, _ = toa_va_can_ho
    cu_dan = _cu_dan(db_session, building_id=toa.id, address="địa chỉ riêng", lat=1.0, lng=2.0)

    dia_chi, lat, lng = noi_o_cua(db_session, cu_dan)

    assert dia_chi == toa.address
    assert lat == toa.lat
    assert lng == toa.lng
