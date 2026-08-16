"""Tuyến chứa điểm dừng loại thùng không được làm sập các lối đọc cũ."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from src.api.serializers import route_dict
from src.db.models import STOP_KIND_THUNG, Bin, PickupRoute, RouteStop
from src.services import route_planner


def _tuyen_co_diem_dung_thung(db_session: Session) -> tuple[PickupRoute, Bin]:
    thung = Bin(code="T-B2-01", name="Thùng ngõ 12", address="12 Hàng Bài", fill_percent=88.0)
    db_session.add(thung)
    tuyen = PickupRoute(service_date=date(2026, 8, 12), window="sang")
    db_session.add(tuyen)
    db_session.flush()
    db_session.add(RouteStop(route_id=tuyen.id, stop_kind=STOP_KIND_THUNG, bin_id=thung.id, seq=1))
    db_session.flush()
    db_session.refresh(tuyen)
    return tuyen, thung


def test_yeu_cau_cua_tra_ve_none_voi_diem_dung_thung(db_session: Session) -> None:
    tuyen, _ = _tuyen_co_diem_dung_thung(db_session)
    assert route_planner.yeu_cau_cua(db_session, tuyen.stops[0]) is None


def test_route_dict_khong_no_va_hien_ten_thung(db_session: Session) -> None:
    tuyen, thung = _tuyen_co_diem_dung_thung(db_session)
    data = route_dict(db_session, tuyen, full=True)
    diem = data["stops"][0]
    assert diem["stop_kind"] == STOP_KIND_THUNG
    assert diem["request_id"] is None
    assert diem["bin_id"] == thung.id
    assert diem["diem_dung_vi"] == "Thùng ngõ 12"
    assert diem["fill_percent"] == 88.0
    assert diem["phone_masked"] == ""


def test_route_diff_bo_qua_diem_dung_thung(db_session: Session) -> None:
    """Diff so bản AI đề xuất với bản người sửa — chỉ tính điểm dừng loại yêu cầu."""
    tuyen, _ = _tuyen_co_diem_dung_thung(db_session)
    diff = route_planner.route_diff(tuyen)
    assert diff["final"] == []
