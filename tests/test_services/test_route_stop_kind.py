"""RouteStop mang được hai loại điểm dừng: yêu cầu của cư dân và thùng đầy."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import (
    STOP_KIND_THUNG,
    STOP_KIND_YEU_CAU,
    Bin,
    PickupRoute,
    RouteStop,
)


def test_diem_dung_loai_thung_khong_can_request_id(db_session: Session) -> None:
    """Điểm dừng loại thùng chỉ có bin_id; request_id để trống được."""
    thung = Bin(code="T-TEST-01", name="Thùng thử", fill_percent=92.0, battery_percent=80.0)
    db_session.add(thung)
    tuyen = PickupRoute(service_date=date(2026, 8, 10), window="sang")
    db_session.add(tuyen)
    db_session.flush()

    db_session.add(RouteStop(route_id=tuyen.id, stop_kind=STOP_KIND_THUNG, bin_id=thung.id, seq=1))
    db_session.flush()

    diem = db_session.scalar(select(RouteStop).where(RouteStop.route_id == tuyen.id))
    assert diem is not None
    assert diem.stop_kind == STOP_KIND_THUNG
    assert diem.bin_id == thung.id
    assert diem.request_id is None


def test_stop_kind_mac_dinh_la_yeu_cau(db_session: Session) -> None:
    """Không truyền stop_kind thì mặc định là điểm dừng loại yêu cầu."""
    tuyen = PickupRoute(service_date=date(2026, 8, 10), window="sang")
    db_session.add(tuyen)
    db_session.flush()

    db_session.add(RouteStop(route_id=tuyen.id, seq=1))
    db_session.flush()

    diem = db_session.scalar(select(RouteStop).where(RouteStop.route_id == tuyen.id))
    assert diem is not None
    assert diem.stop_kind == STOP_KIND_YEU_CAU
    assert diem.bin_id is None
