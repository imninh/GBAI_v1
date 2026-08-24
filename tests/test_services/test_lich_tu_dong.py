"""Test gói P72 — tự tạo chuyến theo lịch cố định + đánh dấu ĐẦY khi không có người.

Mọi thời điểm trong test đều TRUYỀN VÀO, không dùng ``datetime.now()`` — hàm
``bay_gio`` là tham số bắt buộc chính là để test được xác định.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

import pytest

from src.config import reset_settings_cache
from src.db.models import (
    STOP_KIND_THUNG,
    Bin,
    Building,
    CollectionSchedule,
    PickupRoute,
    RouteStop,
    Unit,
    User,
)
from src.services import lich_tu_dong, pickup
from src.services.pickup_lifecycle import CHO_DUYET


@pytest.fixture(autouse=True)
def _reset_config() -> Iterator[None]:
    reset_settings_cache()
    yield
    reset_settings_cache()


def _tao_lich(
    session,
    *,
    building_id: int,
    weekdays: list[int],
    window: str,
    category_code: str = "recyclable",
) -> CollectionSchedule:
    lich = CollectionSchedule(
        building_id=building_id,
        category_code=category_code,
        weekdays=weekdays,
        window=window,
    )
    session.add(lich)
    session.flush()
    return lich


def _tao_toa_va_yeu_cau(
    session,
    *,
    ngay,
    window: str,
    prefix: str,
    so_yeu_cau: int = 1,
    khoi_luong: float = 15.0,
) -> tuple[Building, list]:
    """Toà + yêu cầu đã duyệt cho đúng ngày/khung giờ — nguyên liệu để tạo chuyến."""
    manager = User(email=f"m_{prefix}@demo.vn", full_name="BQL", role="manager", password_hash="x")
    session.add(manager)
    session.flush()

    building = Building(code=f"B-{prefix}", name=f"Toà {prefix}", lat=21.0285, lng=105.8542)
    session.add(building)
    session.flush()

    unit = Unit(building_id=building.id, code=f"U-{prefix}-101")
    session.add(unit)
    session.flush()

    resident = User(
        email=f"r_{prefix}@demo.vn",
        full_name="Cư dân",
        role="resident",
        password_hash="x",
        unit_id=unit.id,
    )
    session.add(resident)
    session.flush()

    cac_yeu_cau = []
    for _ in range(so_yeu_cau):
        req = pickup.create_pickup_request(
            session,
            resident=resident,
            items=[{"name": "Giấy", "category_code": "paper", "qty": 1}],
            est_weight_kg=khoi_luong,
            preferred_date=ngay,
            preferred_window=window,
        )
        if req.status == CHO_DUYET:
            pickup.review_pickup(session, request=req, actor=manager, action="approve")
        cac_yeu_cau.append(req)
    session.flush()
    return building, cac_yeu_cau


def _tao_route_co_thung(session, *, ngay, window: str) -> tuple[Bin, PickupRoute, User]:
    """Chuyến có đúng một điểm dừng loại thùng — nguyên liệu cho test đánh dấu ĐẦY."""
    manager = User(email="m_flag@demo.vn", full_name="BQL", role="manager", password_hash="x")
    session.add(manager)
    session.flush()

    thung = Bin(
        code="BIN-FLAG",
        name="Thùng Flag",
        lat=21.0,
        lng=105.0,
        fill_percent=42.0,
        category_codes=["recyclable"],
    )
    session.add(thung)
    session.flush()

    route = PickupRoute(service_date=ngay, window=window, status="proposed")
    session.add(route)
    session.flush()
    session.add(
        RouteStop(route_id=route.id, stop_kind=STOP_KIND_THUNG, bin_id=thung.id, seq=1)
    )
    session.flush()
    return thung, route, manager


# --- 1. cac_lich_sap_toi ------------------------------------------------

def test_bat_lich_cach_30_phut_bo_lich_cach_90_phut(db_session) -> None:
    bay_gio = datetime(2026, 8, 20, 17, 0)  # một buổi chiều cố định, thứ X
    thu = bay_gio.weekday()

    building = Building(code="B-L", name="Toà L", lat=21.0, lng=105.0)
    db_session.add(building)
    db_session.flush()
    _tao_lich(db_session, building_id=building.id, weekdays=[thu], window="17:30-19:00")  # 30 phút sau → bắt
    _tao_lich(db_session, building_id=building.id, weekdays=[thu], window="18:30-20:00")  # 90 phút sau → bỏ
    db_session.commit()

    ket = lich_tu_dong.cac_lich_sap_toi(db_session, bay_gio=bay_gio, truoc_bao_lau_phut=60)
    assert len(ket) == 1
    assert ket[0].window == "17:30-19:00"


def test_lich_khong_dung_thu_khong_duoc_chon(db_session) -> None:
    bay_gio = datetime(2026, 8, 20, 17, 0)
    khac_thu = (bay_gio.weekday() + 1) % 7  # đúng giờ nhưng khác thứ trong tuần

    building = Building(code="B-W", name="Toà W", lat=21.0, lng=105.0)
    db_session.add(building)
    db_session.flush()
    _tao_lich(db_session, building_id=building.id, weekdays=[khac_thu], window="17:30-19:00")
    db_session.commit()

    ket = lich_tu_dong.cac_lich_sap_toi(db_session, bay_gio=bay_gio, truoc_bao_lau_phut=60)
    assert ket == []


def test_window_rong_hoac_sai_dinh_dang_bo_qua(db_session) -> None:
    bay_gio = datetime(2026, 8, 20, 17, 0)
    thu = bay_gio.weekday()

    building = Building(code="B-X", name="Toà X", lat=21.0, lng=105.0)
    db_session.add(building)
    db_session.flush()
    _tao_lich(db_session, building_id=building.id, weekdays=[thu], window="")     # rỗng
    _tao_lich(db_session, building_id=building.id, weekdays=[thu], window="tối")  # sai định dạng
    db_session.commit()

    ket = lich_tu_dong.cac_lich_sap_toi(db_session, bay_gio=bay_gio, truoc_bao_lau_phut=60)
    assert ket == []


# --- 2. tao_chuyen_tu_lich ----------------------------------------------

def test_tao_chuyen_hai_lan_khong_tang_so_route(db_session) -> None:
    """Gọi hai lần liên tiếp → tổng số PickupRoute không tăng ở lần thứ hai."""
    bay_gio = datetime(2026, 8, 20, 17, 30)
    thu = bay_gio.weekday()
    window = "18:00-20:00"

    building, _ = _tao_toa_va_yeu_cau(db_session, ngay=bay_gio.date(), window=window, prefix="DUP")
    _tao_lich(db_session, building_id=building.id, weekdays=[thu], window=window)
    db_session.commit()

    ket1 = lich_tu_dong.tao_chuyen_tu_lich(db_session, bay_gio=bay_gio, truoc_bao_lau_phut=60)
    so_route_sau_lan1 = db_session.query(PickupRoute).count()
    assert ket1["so_chuyen_tao"] >= 1
    assert so_route_sau_lan1 >= 1

    ket2 = lich_tu_dong.tao_chuyen_tu_lich(db_session, bay_gio=bay_gio, truoc_bao_lau_phut=60)
    so_route_sau_lan2 = db_session.query(PickupRoute).count()
    assert so_route_sau_lan2 == so_route_sau_lan1  # không tăng
    assert ket2["so_chuyen_tao"] == 0
    assert ket2["so_lich_bo_vi_da_co"] >= 1


def test_chuyen_tu_dong_co_nguon_tao_va_status_proposed(db_session) -> None:
    bay_gio = datetime(2026, 8, 20, 17, 30)
    thu = bay_gio.weekday()
    window = "18:00-20:00"

    building, _ = _tao_toa_va_yeu_cau(db_session, ngay=bay_gio.date(), window=window, prefix="NGUON")
    _tao_lich(db_session, building_id=building.id, weekdays=[thu], window=window)
    db_session.commit()

    ket = lich_tu_dong.tao_chuyen_tu_lich(db_session, bay_gio=bay_gio, truoc_bao_lau_phut=60)
    assert ket["so_chuyen_tao"] >= 1

    cac_route = db_session.query(PickupRoute).all()
    assert cac_route, "Phải có ít nhất một chuyến được tạo"
    for route in cac_route:
        assert route.nguon_tao == "tu_dong"
        assert route.status == "proposed"


def test_khong_yeu_cau_khong_tao_chuyen_rong(db_session) -> None:
    bay_gio = datetime(2026, 8, 20, 17, 30)
    thu = bay_gio.weekday()
    window = "18:00-20:00"

    building = Building(code="B-E", name="Toà E", lat=21.0, lng=105.0)
    db_session.add(building)
    db_session.flush()
    _tao_lich(db_session, building_id=building.id, weekdays=[thu], window=window)
    db_session.commit()

    ket = lich_tu_dong.tao_chuyen_tu_lich(db_session, bay_gio=bay_gio, truoc_bao_lau_phut=60)
    assert ket["so_chuyen_tao"] == 0
    assert ket["so_lich_bo_vi_khong_yeu_cau"] == 1
    assert db_session.query(PickupRoute).count() == 0  # không tạo chuyến rỗng


# --- 3. danh_dau_day_khi_khong_co_nguoi / bo_danh_dau_day ---------------

def test_danh_dau_day_giu_nguyen_fill_percent(db_session) -> None:
    ngay = datetime(2026, 8, 20).date()
    thung, route, manager = _tao_route_co_thung(db_session, ngay=ngay, window="18:00-20:00")
    db_session.commit()

    truoc = thung.fill_percent
    so = lich_tu_dong.danh_dau_day_khi_khong_co_nguoi(
        db_session, actor=manager, route_id=route.id, ly_do="không có xe"
    )
    assert so == 1

    db_session.refresh(thung)
    assert thung.dat_day_thu_cong is True
    # Khẳng định: đặt cờ ĐẦY nhưng KHÔNG đụng số đo cảm biến
    assert thung.fill_percent == truoc


def test_bo_danh_dau_day_gỡ_cờ(db_session) -> None:
    ngay = datetime(2026, 8, 20).date()
    thung, route, manager = _tao_route_co_thung(db_session, ngay=ngay, window="18:00-20:00")
    db_session.commit()

    lich_tu_dong.danh_dau_day_khi_khong_co_nguoi(
        db_session, actor=manager, route_id=route.id, ly_do="test"
    )
    db_session.refresh(thung)
    assert thung.dat_day_thu_cong is True

    so = lich_tu_dong.bo_danh_dau_day(db_session, actor=manager, route_id=route.id)
    assert so == 1

    db_session.refresh(thung)
    assert thung.dat_day_thu_cong is False
