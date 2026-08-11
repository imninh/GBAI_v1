"""Tuyến gộp cả thùng đang đầy lẫn yêu cầu của cư dân."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from src.db.models import STOP_KIND_THUNG, Bin, utcnow
from src.services import route_planner


def _thung_day(code: str, lat: float, lng: float, fill: float = 92.0) -> Bin:
    """Thùng vừa báo về, pin đầy, mức rác vượt ngưỡng → trạng thái ``can_gom``."""
    return Bin(
        code=code,
        name=f"Thùng {code}",
        lat=lat,
        lng=lng,
        capacity_liters=240.0,
        fill_percent=fill,
        battery_percent=90.0,
        last_seen_at=utcnow(),
        is_active=True,
    )


def test_thung_day_tro_thanh_diem_dung(db_session: Session) -> None:
    db_session.add(_thung_day("T-01", 21.0285, 105.8542))
    db_session.flush()

    tuyen = route_planner.propose_route(db_session, service_date=date.today(), window="sang")

    assert len(tuyen.stops) == 1
    assert tuyen.stops[0].stop_kind == STOP_KIND_THUNG
    assert tuyen.stops[0].request_id is None
    assert tuyen.status == "proposed"


def test_khong_co_thung_day_thi_khong_co_diem_dung_nao(db_session: Session) -> None:
    """Thùng chưa đầy không được kéo vào tuyến."""
    db_session.add(_thung_day("T-02", 21.0285, 105.8542, fill=10.0))
    db_session.flush()

    try:
        route_planner.propose_route(db_session, service_date=date.today(), window="sang")
    except ValueError as loi:
        assert "không có thùng nào cần gom" in str(loi)
    else:
        raise AssertionError("Phải báo lỗi khi không có ứng viên nào")


def test_thung_mat_ket_noi_khong_duoc_vao_tuyen(db_session: Session) -> None:
    """Thùng offline vẫn còn lưu 92% của lần báo cuối — đi tới đó là đi mò."""
    thung = _thung_day("T-03", 21.0285, 105.8542)
    thung.last_seen_at = utcnow() - timedelta(days=3)
    db_session.add(thung)
    db_session.flush()

    try:
        route_planner.propose_route(db_session, service_date=date.today(), window="sang")
    except ValueError:
        pass
    else:
        raise AssertionError("Thùng mất kết nối không được xếp vào tuyến")


def test_khoi_luong_thung_la_uoc_luong_tu_the_tich(db_session: Session) -> None:
    # Mức đầy phải VƯỢT ngưỡng cảnh báo (`bin_fill_alert_percent`, mặc định 80)
    # thì thùng mới ở trạng thái `can_gom` và mới được xếp vào tuyến.
    db_session.add(_thung_day("T-04", 21.0285, 105.8542, fill=100.0))
    db_session.flush()

    tuyen = route_planner.propose_route(db_session, service_date=date.today(), window="sang")

    # 240 L × 100% × 0,08 kg/L = 19,2 kg
    assert abs(tuyen.total_weight_kg - 19.2) < 0.05


def test_ly_do_gop_noi_ro_co_bao_nhieu_thung(db_session: Session) -> None:
    db_session.add(_thung_day("T-05", 21.0285, 105.8542))
    db_session.add(_thung_day("T-06", 21.0290, 105.8548))
    db_session.flush()

    tuyen = route_planner.propose_route(db_session, service_date=date.today(), window="sang")

    ly_do = " ".join(tuyen.reasoning["criteria"])
    assert "2 thùng đang đầy" in ly_do
    assert "0 yêu cầu của cư dân" in ly_do
