"""Điểm dừng trong tuyến phải mang toạ độ để vẽ lên bản đồ duyệt."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from src.api.serializers import route_dict
from src.db.models import (
    STOP_KIND_THUNG,
    STOP_KIND_YEU_CAU,
    Bin,
    Building,
    PickupRequest,
    PickupRoute,
    RouteStop,
    Unit,
    User,
)


def _them_tuyen(db_session: Session) -> PickupRoute:
    tuyen = PickupRoute(service_date=date(2026, 8, 15), window="sang")
    db_session.add(tuyen)
    db_session.flush()
    return tuyen


def test_diem_dung_thung_mang_toa_do_rieng(db_session: Session) -> None:
    """Thùng có toạ độ và địa chỉ của chính nó, không mượn của toà nhà."""
    thung = Bin(
        code="T-TD-01",
        name="Thùng Trần Duy Hưng",
        address="12 Trần Duy Hưng",
        lat=21.0310,
        lng=105.8040,
        fill_percent=90.0,
    )
    db_session.add(thung)
    tuyen = _them_tuyen(db_session)
    db_session.add(RouteStop(route_id=tuyen.id, stop_kind=STOP_KIND_THUNG, bin_id=thung.id, seq=1))
    db_session.flush()
    db_session.refresh(tuyen)

    diem = route_dict(db_session, tuyen, full=True)["stops"][0]
    assert diem["stop_kind"] == STOP_KIND_THUNG
    assert diem["lat"] == 21.0310
    assert diem["lng"] == 105.8040
    assert diem["dia_chi"] == "12 Trần Duy Hưng"


def test_diem_dung_yeu_cau_muon_toa_do_toa_nha(db_session: Session) -> None:
    """Yêu cầu của cư dân không có toạ độ riêng — lấy của toà nhà đang ở."""
    toa = Building(code="S9", name="Toà S9", address="9 Bà Triệu, Hoàn Kiếm", lat=21.0293, lng=105.8542)
    cu_dan = User(email="r-toa-do@test.vn", full_name="Lê Thị Hồng", role="resident", password_hash="x")
    db_session.add_all([toa, cu_dan])
    db_session.flush()
    don_vi = Unit(building_id=toa.id, code="S9-0101")
    db_session.add(don_vi)
    db_session.flush()
    yeu_cau = PickupRequest(
        resident_id=cu_dan.id,
        unit_id=don_vi.id,
        items=[{"name": "Tủ quần áo", "category_code": "bulky", "qty": 1}],
        weight_max_kg=40.0,
    )
    db_session.add(yeu_cau)
    tuyen = _them_tuyen(db_session)
    db_session.add(RouteStop(route_id=tuyen.id, stop_kind=STOP_KIND_YEU_CAU, request_id=yeu_cau.id, seq=1))
    db_session.flush()
    db_session.refresh(tuyen)

    diem = route_dict(db_session, tuyen, full=True)["stops"][0]
    assert diem["stop_kind"] == STOP_KIND_YEU_CAU
    assert diem["lat"] == 21.0293
    assert diem["lng"] == 105.8542
    assert diem["dia_chi"] == "9 Bà Triệu, Hoàn Kiếm"


def test_thung_khong_co_toa_do_thi_seri_hoa_thanh_null(db_session: Session) -> None:
    """Toạ độ thiếu phải ra `null` — 0,0 là một chỗ thật giữa vịnh Guinea."""
    thung = Bin(code="T-NULL-01", name="Thùng chưa gắn toạ độ", fill_percent=95.0)
    db_session.add(thung)
    tuyen = _them_tuyen(db_session)
    db_session.add(RouteStop(route_id=tuyen.id, stop_kind=STOP_KIND_THUNG, bin_id=thung.id, seq=1))
    db_session.flush()
    db_session.refresh(tuyen)

    diem = route_dict(db_session, tuyen, full=True)["stops"][0]
    assert diem["lat"] is None
    assert diem["lng"] is None
    assert diem["lat"] != 0.0
    assert diem["lng"] != 0.0


def test_khong_full_thi_khong_co_khoa_stops(db_session: Session) -> None:
    """Bản rút gọn vẫn không có danh sách điểm dừng — hợp đồng cũ giữ nguyên."""
    tuyen = _them_tuyen(db_session)

    data = route_dict(db_session, tuyen, full=False)
    assert "stops" not in data
