"""Điểm dừng trong tuyến phải mang địa chỉ để người đi thu gom đến được chỗ.

Trước gói P25, điểm dừng loại "yêu cầu" chỉ phát mã căn kiểu ``S1-0805`` —
người cầm điện thoại đi thu gom không biết đến chỗ nào. Nay phát thêm
``dia_chi``: thùng giữ địa chỉ của chính nó, yêu cầu ghép mã căn với địa chỉ
toà nhà, và khi toà chưa có địa chỉ thì lui về mã căn. Không được thêm truy
vấn theo từng điểm dừng — đây là màn hình mở liên tục.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import event
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

# Danh sách khoá của một điểm dừng là HỢP ĐỒNG với frontend: màn nhân viên vệ
# sinh và màn quản lý đều đọc trực tiếp. Bớt một khoá là bỏ sót một thứ người
# dùng nhìn. Gói P25 chỉ THÊM nội dung `dia_chi`, không thêm hay bớt khoá nào.
HOP_DONG_KHOA: list[str] = [
    "stop_id",
    "seq",
    "stop_kind",
    "request_id",
    "bin_id",
    "diem_dung_vi",
    "dia_chi",
    "lat",
    "lng",
    "fill_percent",
    "unit",
    "resident_name",
    "phone_masked",
    "weight_max_kg",
    "items",
    "done_at",
    "issue",
    "issue_note",
    "actual_weight_kg",
]


def _them_tuyen(db_session: Session) -> PickupRoute:
    tuyen = PickupRoute(service_date=date(2026, 8, 15), window="sang")
    db_session.add(tuyen)
    db_session.flush()
    return tuyen


def _them_yeu_cau(db_session: Session, toa: Building, ma_can: str) -> PickupRequest:
    cu_dan = User(email=f"r-{ma_can.lower()}@test.vn", full_name="Cư dân test", role="resident", password_hash="x")
    db_session.add(cu_dan)
    db_session.flush()
    can = Unit(building_id=toa.id, code=ma_can)
    db_session.add(can)
    db_session.flush()
    yeu_cau = PickupRequest(
        resident_id=cu_dan.id,
        unit_id=can.id,
        items=[{"name": "Tủ quần áo", "category_code": "bulky", "qty": 1}],
        weight_max_kg=40.0,
    )
    db_session.add(yeu_cau)
    db_session.flush()
    return yeu_cau


def _diem_dau_tien(db_session: Session, tuyen: PickupRoute) -> dict:
    db_session.refresh(tuyen)
    return route_dict(db_session, tuyen, full=True)["stops"][0]


def test_diem_dung_yeu_cau_co_dia_chi_cua_toa(db_session: Session) -> None:
    """Yêu cầu ghép mã căn với địa chỉ toà nhà — người đi thu gom tìm được chỗ."""
    toa = Building(
        code="S1",
        name="Sunrise Residence — Toà S1",
        address="25 Lý Thường Kiệt, Hoàn Kiếm, Hà Nội",
        lat=21.0271,
        lng=105.8519,
    )
    db_session.add(toa)
    db_session.flush()
    yeu_cau = _them_yeu_cau(db_session, toa, "S1-0805")
    tuyen = _them_tuyen(db_session)
    db_session.add(RouteStop(route_id=tuyen.id, stop_kind=STOP_KIND_YEU_CAU, request_id=yeu_cau.id, seq=1))
    db_session.flush()

    diem = _diem_dau_tien(db_session, tuyen)
    assert diem["dia_chi"] == "Căn S1-0805 · 25 Lý Thường Kiệt, Hoàn Kiếm, Hà Nội"


def test_diem_dung_thung_giu_nguyen_dia_chi_cu(db_session: Session) -> None:
    """Thùng giữ nguyên địa chỉ của chính nó — không ghép gì thêm."""
    thung = Bin(
        code="T-DC-01",
        name="Phố Đinh Tiên Hoàng (Bờ Hồ)",
        address="Phố Đinh Tiên Hoàng, quận Hoàn Kiếm, Hà Nội",
        lat=21.0285,
        lng=105.8542,
        fill_percent=90.0,
    )
    db_session.add(thung)
    tuyen = _them_tuyen(db_session)
    db_session.add(RouteStop(route_id=tuyen.id, stop_kind=STOP_KIND_THUNG, bin_id=thung.id, seq=1))
    db_session.flush()

    diem = _diem_dau_tien(db_session, tuyen)
    assert diem["dia_chi"] == "Phố Đinh Tiên Hoàng, quận Hoàn Kiếm, Hà Nội"


def test_toa_chua_co_dia_chi_thi_lui_ve_ma_can(db_session: Session) -> None:
    """Toà chưa có địa chỉ thì `dia_chi` bằng đúng mã căn, không cụt đuôi."""
    toa = Building(code="S7", name="Toà S7", address="", lat=21.0271, lng=105.8519)
    db_session.add(toa)
    db_session.flush()
    yeu_cau = _them_yeu_cau(db_session, toa, "S7-0101")
    tuyen = _them_tuyen(db_session)
    db_session.add(RouteStop(route_id=tuyen.id, stop_kind=STOP_KIND_YEU_CAU, request_id=yeu_cau.id, seq=1))
    db_session.flush()

    diem = _diem_dau_tien(db_session, tuyen)
    assert diem["dia_chi"] == "S7-0101"
    assert diem["dia_chi"]
    assert "·" not in diem["dia_chi"]


def test_khong_mat_khoa_nao_trong_payload(db_session: Session) -> None:
    """Tập khoá của một điểm dừng phải giữ nguyên — chỉ thêm, không bớt."""
    toa = Building(
        code="K1",
        name="Toà K1",
        address="25 Lý Thường Kiệt, Hoàn Kiếm, Hà Nội",
        lat=21.0271,
        lng=105.8519,
    )
    db_session.add(toa)
    db_session.flush()
    yeu_cau = _them_yeu_cau(db_session, toa, "K1-0101")
    tuyen = _them_tuyen(db_session)
    db_session.add(RouteStop(route_id=tuyen.id, stop_kind=STOP_KIND_YEU_CAU, request_id=yeu_cau.id, seq=1))
    db_session.flush()

    diem = _diem_dau_tien(db_session, tuyen)
    assert set(diem.keys()) == set(HOP_DONG_KHOA)


def _dem_sql_cho_tuyen(db_session: Session, ma_tuyen: int) -> int:
    """Số câu SQL phát ra khi seri hoá đầy đủ một tuyến."""
    so_cau: list[str] = []

    def _dem(conn, cursor, statement, parameters, context, executemany) -> None:
        so_cau.append(str(statement))

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", _dem)
    try:
        tuyen = db_session.get(PickupRoute, ma_tuyen)
        route_dict(db_session, tuyen, full=True)
        return len(so_cau)
    finally:
        event.remove(engine, "before_cursor_execute", _dem)


def _tuyen_voi_so_diem(db_session: Session, so_diem: int, cac_toa: list[Building], tien_to: str) -> PickupRoute:
    tuyen = _them_tuyen(db_session)
    for i in range(so_diem):
        toa = cac_toa[i % len(cac_toa)]
        yeu_cau = _them_yeu_cau(db_session, toa, f"{tien_to}-{i + 1:02d}")
        db_session.add(RouteStop(route_id=tuyen.id, stop_kind=STOP_KIND_YEU_CAU, request_id=yeu_cau.id, seq=i + 1))
    db_session.flush()
    return tuyen


def test_khong_truy_van_trong_vong_lap(db_session: Session) -> None:
    """Số câu SQL phải hằng số — không tăng theo số điểm dừng của tuyến.

    Tuyến 6 điểm dừng thuộc 3 toà không được phát ra nhiều truy vấn hơn tuyến
    2 điểm dừng: thực thể được gom một lần trước vòng lặp.
    """
    cac_toa = [
        Building(code="D1", name="Toà D1", address="25 Lý Thường Kiệt, Hoàn Kiếm, Hà Nội", lat=21.0271, lng=105.8519),
        Building(code="D2", name="Toà D2", address="5 Đinh Tiên Hoàng, Hoàn Kiếm, Hà Nội", lat=21.0284, lng=105.8531),
        Building(code="D3", name="Toà D3", address="26 Lò Sũ, Hoàn Kiếm, Hà Nội", lat=21.0303, lng=105.8554),
    ]
    db_session.add_all(cac_toa)
    db_session.flush()
    tuyen_2 = _tuyen_voi_so_diem(db_session, 2, cac_toa, "A")
    tuyen_6 = _tuyen_voi_so_diem(db_session, 6, cac_toa, "B")
    db_session.flush()
    # Đo từ bộ nhớ đệm rỗng cho cả hai tuyến, nếu không tuyến dựng trước sẽ nằm
    # sẵn trong identity map và bỏ được câu lấy tuyến — so không cùng thước đo.
    db_session.expunge_all()

    cau_tuyen_2 = _dem_sql_cho_tuyen(db_session, tuyen_2.id)
    db_session.expunge_all()
    cau_tuyen_6 = _dem_sql_cho_tuyen(db_session, tuyen_6.id)

    assert cau_tuyen_6 == cau_tuyen_2, "Seri hoá tuyến lớn hơn không được phát ra nhiều câu SQL hơn"


def test_ba_toa_seed_deu_co_dia_chi(db_session: Session) -> None:
    """Sau seed, cả ba toà đều có địa chỉ khác rỗng — có sẵn để đưa ra."""
    from scripts.seed import seed_buildings

    toa = seed_buildings(db_session)
    db_session.commit()

    assert len(toa) == 3
    for ma in ("S1", "S2", "S3"):
        assert toa[ma].address, f"Toà {ma} phải có địa chỉ sau seed"
