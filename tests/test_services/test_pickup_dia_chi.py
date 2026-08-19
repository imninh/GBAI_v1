"""Gói P52 — tạo yêu cầu thu gom cho cư dân không có căn hộ.

Trước gói này, ``create_pickup_request`` chặn cứng ``unit_id is None`` nên 600
tài khoản nhập từ dữ liệu GIS (hộ dân lẻ trên phố) không tạo được yêu cầu. Nay
nơi ở tách làm hai khái niệm: quan hệ hành chính (``unit_id``) và toạ độ địa lý
(``address``/``lat``/``lng``). Không đẻ căn hộ giả cho 600 người.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from src.db.models import Building, PickupRequest, Unit, User
from src.services import pickup
from src.services.pickup_lifecycle import CHO_NHAN

_MON = {"name": "Tủ nhỏ", "category_code": "bulky", "qty": 1, "est_weight_kg": 8}


@pytest.fixture
def toa_va_can_ho(db_session: Session) -> tuple[Building, Unit]:
    toa = Building(code="P52", name="Toà P52", address="123 Lý Thường Kiệt, Hà Nội", lat=21.0271, lng=105.8519)
    db_session.add(toa)
    db_session.flush()
    can_ho = Unit(building_id=toa.id, code="P52-01")
    db_session.add(can_ho)
    db_session.flush()
    return toa, can_ho


def _cu_dan(db_session: Session, *, unit_id: int | None = None, address: str = "", lat=None, lng=None) -> User:
    cu_dan = User(
        email="cu-dan-p52@demo.vn",
        full_name="Cư dân P52",
        role="resident",
        password_hash="x",
        unit_id=unit_id,
        address=address,
        lat=lat,
        lng=lng,
    )
    db_session.add(cu_dan)
    db_session.flush()
    return cu_dan


def test_co_can_ho_khong_dia_chi_tao_duoc_unit_id_dung(
    db_session: Session, toa_va_can_ho: tuple[Building, Unit]
) -> None:
    """(a) Cư dân có căn hộ, không truyền địa chỉ → tạo được, unit_id giữ nguyên."""
    _, can_ho = toa_va_can_ho
    cu_dan = _cu_dan(db_session, unit_id=can_ho.id)

    yeu_cau = pickup.create_pickup_request(db_session, resident=cu_dan, items=[_MON], est_weight_kg=8.0)

    assert yeu_cau.unit_id == can_ho.id
    assert yeu_cau.address == ""  # không truyền → không có điểm lấy hàng riêng
    assert yeu_cau.status == CHO_NHAN


def test_khong_can_ho_khong_dia_chi_nao_thi_value_error(db_session: Session) -> None:
    """(b) Không căn hộ, không địa chỉ ở đâu cả → ValueError."""
    cu_dan = _cu_dan(db_session)

    with pytest.raises(ValueError, match="cần nhập địa chỉ"):
        pickup.create_pickup_request(db_session, resident=cu_dan, items=[_MON], est_weight_kg=8.0)


def test_khong_can_ho_truyen_address_tao_duoc_unit_id_none(
    db_session: Session,
) -> None:
    """(c) Không căn hộ, truyền `address` → tạo được, unit_id None, address đúng."""
    cu_dan = _cu_dan(db_session)

    yeu_cau = pickup.create_pickup_request(
        db_session,
        resident=cu_dan,
        items=[_MON],
        est_weight_kg=8.0,
        address="45 Hai Bà Trưng, Hoàn Kiếm, Hà Nội",
        lat=21.0199,
        lng=105.8528,
    )

    assert yeu_cau.unit_id is None
    assert yeu_cau.address == "45 Hai Bà Trưng, Hoàn Kiếm, Hà Nội"
    assert yeu_cau.lat == 21.0199
    assert yeu_cau.lng == 105.8528


def test_khong_can_ho_khong_truyen_nhung_user_co_address_lay_noi_o_cua_nguoi_do(
    db_session: Session,
) -> None:
    """(d) Không căn hộ, KHÔNG truyền `address` nhưng user có nơi ở → lấy nơi ở đó."""
    cu_dan = _cu_dan(db_session, address="Phố X, Hà Nội", lat=21.0100, lng=105.8400)

    yeu_cau = pickup.create_pickup_request(db_session, resident=cu_dan, items=[_MON], est_weight_kg=8.0)

    assert yeu_cau.unit_id is None
    assert yeu_cau.address == "Phố X, Hà Nội"
    assert yeu_cau.lat == 21.0100
    assert yeu_cau.lng == 105.8400


def test_co_can_ho_va_truyen_address_thi_address_theo_yeu_cau_unit_id_giu(
    db_session: Session, toa_va_can_ho: tuple[Building, Unit]
) -> None:
    """(e) Có căn hộ VÀ truyền `address` → address theo yêu cầu, unit_id vẫn giữ
    để BQL của toà vẫn duyệt được."""
    _, can_ho = toa_va_can_ho
    cu_dan = _cu_dan(db_session, unit_id=can_ho.id)

    yeu_cau = pickup.create_pickup_request(
        db_session,
        resident=cu_dan,
        items=[_MON],
        est_weight_kg=8.0,
        address="Tầng trệt toà S3, lấy tại cổng sau",
    )

    assert yeu_cau.unit_id == can_ho.id
    assert yeu_cau.address == "Tầng trệt toà S3, lấy tại cổng sau"


def test_khong_can_ho_khong_dia_chi_nhung_items_rong_khong_loi_trung(
    db_session: Session,
) -> None:
    """Items rỗng nhưng có khoảng khối lượng hợp lệ vẫn phải báo lỗi địa chỉ
    TRƯỚC khi kiểm khối lượng — không được lẫn lộn thứ tự báo lỗi."""
    cu_dan = _cu_dan(db_session)

    with pytest.raises(ValueError, match="cần nhập địa chỉ"):
        pickup.create_pickup_request(
            db_session, resident=cu_dan, items=[], est_weight_kg=0, weight_min_kg=3, weight_max_kg=8
        )


def test_yeu_cau_tao_duoc_va_ghi_vao_bang(db_session: Session) -> None:
    """Bản ghi PickupRequest lưu đủ address/lat/lng khi tạo bằng luồng mới."""
    cu_dan = _cu_dan(db_session)

    yeu_cau = pickup.create_pickup_request(
        db_session,
        resident=cu_dan,
        items=[_MON],
        est_weight_kg=8.0,
        address="Số 1, Hàng Bạc, Hoàn Kiếm, Hà Nội",
        lat=21.0350,
        lng=105.8520,
    )
    db_session.flush()

    da_luu = db_session.get(PickupRequest, yeu_cau.id)
    assert da_luu is not None
    assert da_luu.address == "Số 1, Hàng Bạc, Hoàn Kiếm, Hà Nội"
    assert da_luu.lat == 21.0350
    assert da_luu.lng == 105.8520
