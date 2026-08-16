"""Cơ chế điểm thưởng (gói P29) và hai chuỗi trạng thái chết trong `me_history`.

Không test nào chạm mạng. Dùng fixture ``db_session`` của ``tests/conftest.py``
(CSDL SQLite trong bộ nhớ, đã seed danh mục rác).

Ba ý được giữ bằng test:
* điểm KHÔNG BAO GIỜ tính trên cận ước lượng của AI — chỉ trên số người cân;
* một yêu cầu = tối đa một dòng sổ cái;
* `me_history` phải đếm `hoan_tat` là "đã thu" và loại `da_huy`/`tu_choi`.
"""

from __future__ import annotations

from sqlalchemy import func, select

from src.db.models import Building, DiemThuongLog, PickupRequest, Unit, User
from src.services import pickup_flow
from src.services.diem_thuong import DIEM_MOI_KG, DIEM_MOI_MON, tinh_diem, trao_diem


def _cu_dan(session) -> User:
    cu_dan = User(email="r-diem@test.vn", full_name="Nguyễn Nhận Điểm", role="resident", password_hash="x")
    session.add(cu_dan)
    session.flush()
    return cu_dan


_ma_toa = [0]


def _toa_va_can_ho(session) -> Unit:
    _ma_toa[0] += 1
    toa = Building(code=f"D{_ma_toa[0]}", name=f"Toà D{_ma_toa[0]}")
    session.add(toa)
    session.flush()
    can_ho = Unit(building_id=toa.id, code=f"D{_ma_toa[0]}-0101")
    session.add(can_ho)
    session.flush()
    return can_ho


def _yeu_cau(
    session,
    *,
    cu_dan: User,
    status: str,
    weight_confirmed_kg: float | None,
    items: list[dict],
    min_kg: float = 10.0,
    max_kg: float = 20.0,
) -> PickupRequest:
    can_ho = _toa_va_can_ho(session)
    yeu_cau = PickupRequest(
        resident_id=cu_dan.id,
        unit_id=can_ho.id,
        items=items,
        weight_min_kg=min_kg,
        weight_max_kg=max_kg,
        est_weight_kg=(min_kg + max_kg) / 2,
        status=status,
        weight_confirmed_kg=weight_confirmed_kg,
    )
    session.add(yeu_cau)
    session.flush()
    return yeu_cau


# --- Hàm thuần `tinh_diem` -------------------------------------------------


def test_diem_tinh_tren_so_can_that_khong_phai_uoc_luong(db_session) -> None:
    """Lời hứa lớn nhất của sản phẩm: yêu cầu có khoảng 10–20 kg, người cân 12 kg
    → phần khối lượng phải là 12 × DIEM_MOI_KG, KHÔNG phải 20 × … (cận AI)."""
    ket_qua = tinh_diem(12.0, [{"name": "chai", "category_code": "recyclable_plastic", "qty": 1}])

    assert ket_qua["diem_khoi_luong"] == int(round(12.0 * DIEM_MOI_KG))
    assert ket_qua["diem_khoi_luong"] != int(round(20.0 * DIEM_MOI_KG))


def test_thang_vat_lieu_nguy_hai_cao_hon_nhua(db_session) -> None:
    """Cùng số cân, cùng số món: một món hazardous phải ra điểm cao hơn hẳn nhựa."""
    nguy_hai = tinh_diem(10.0, [{"name": "pin", "category_code": "hazardous", "qty": 1}])
    nhua = tinh_diem(10.0, [{"name": "chai", "category_code": "recyclable_plastic", "qty": 1}])

    assert nguy_hai["diem_vat_lieu"] > nhua["diem_vat_lieu"]
    assert nguy_hai["diem"] > nhua["diem"]


def test_ma_nhom_la_khong_lam_no(db_session) -> None:
    """Mã lạ → 0 điểm không nổ; mã rỗng → bỏ qua; thiếu qty / qty rác → coi là 1."""
    ket_qua = tinh_diem(
        5.0,
        [
            {"name": "lạ", "category_code": "chua_co_nhom", "qty": 2},
            {"name": "rỗng", "category_code": ""},
            {"name": "thiếu qty", "category_code": "recyclable_glass"},
            {"name": "qty rác", "category_code": "recyclable_metal", "qty": "abc"},
        ],
    )

    assert ket_qua["diem_vat_lieu"] == DIEM_MOI_MON["recyclable_glass"] * 1 + DIEM_MOI_MON["recyclable_metal"] * 1
    assert "" not in ket_qua["chi_tiet"]
    assert ket_qua["chi_tiet"]["chua_co_nhom"]["diem"] == 0


def test_tong_diem_bang_hai_phan_cong_lai(db_session) -> None:
    cac_bo = [
        (12.0, [{"name": "a", "category_code": "hazardous", "qty": 2}]),
        (5.5, [{"name": "b", "category_code": "recyclable_paper", "qty": 3}, {"name": "c", "category_code": "other"}]),
        (0.0, []),
        (-3.0, [{"name": "d", "category_code": "recyclable_metal", "qty": 1}]),
    ]
    for can, items in cac_bo:
        ket_qua = tinh_diem(can, items)
        assert ket_qua["diem"] == ket_qua["diem_khoi_luong"] + ket_qua["diem_vat_lieu"]


def test_chi_tiet_bao_phu_moi_ma_co_mon(db_session) -> None:
    items = [
        {"name": "a", "category_code": "hazardous", "qty": 1},
        {"name": "b", "category_code": "recyclable_plastic", "qty": 2},
        {"name": "c", "category_code": "", "qty": 1},
    ]
    ket_qua = tinh_diem(10.0, items)

    for ma in ("hazardous", "recyclable_plastic"):
        assert ma in ket_qua["chi_tiet"], f"'{ma}' phải có mặt trong chi_tiet"
    assert "" not in ket_qua["chi_tiet"]
    assert sum(o["diem"] for o in ket_qua["chi_tiet"].values()) == ket_qua["diem_vat_lieu"]


# --- Hàm trao điểm `trao_diem` ----------------------------------------------


def test_khong_hoan_tat_thi_khong_trao_diem(db_session) -> None:
    cu_dan = _cu_dan(db_session)
    yeu_cau = _yeu_cau(
        db_session,
        cu_dan=cu_dan,
        status="tranh_chap",
        weight_confirmed_kg=5.0,
        items=[{"name": "tủ", "category_code": "bulky", "qty": 1}],
    )
    truoc = cu_dan.green_points

    ket_qua = trao_diem(db_session, yeu_cau)
    db_session.flush()

    assert ket_qua is None
    assert cu_dan.green_points == truoc, "Tranh chấp không được cộng điểm"
    so_cai = db_session.scalar(select(func.count(DiemThuongLog.id)))
    assert so_cai == 0


def test_khong_trao_hai_lan_cho_mot_yeu_cau(db_session) -> None:
    cu_dan = _cu_dan(db_session)
    yeu_cau = _yeu_cau(
        db_session,
        cu_dan=cu_dan,
        status="hoan_tat",
        weight_confirmed_kg=12.0,
        items=[{"name": "chai", "category_code": "recyclable_plastic", "qty": 1}],
    )

    lan_1 = trao_diem(db_session, yeu_cau)
    db_session.flush()
    assert lan_1 is not None
    diem_truoc = cu_dan.green_points

    lan_2 = trao_diem(db_session, yeu_cau)
    db_session.flush()

    assert lan_2 is None, "Lần hai phải bị chặn — một yêu cầu tối đa một dòng sổ cái"
    so_cai = db_session.scalar(select(func.count(DiemThuongLog.id)))
    assert so_cai == 1
    assert cu_dan.green_points == diem_truoc, "green_points không được cộng lần hai"


def test_di_qua_xac_nhan_khoi_luong_thi_diem_tang(db_session) -> None:
    """Đi đường thật: xac_nhan_khoi_luong với số cân trong khoảng → hoan_tat → điểm tăng."""
    cu_dan = _cu_dan(db_session)
    nguoi_can = User(email="nv-can@test.vn", full_name="Lê Cân", role="cleaner", password_hash="x")
    db_session.add(nguoi_can)
    db_session.flush()
    yeu_cau = _yeu_cau(
        db_session,
        cu_dan=cu_dan,
        status="da_giao_don_vi",
        weight_confirmed_kg=None,
        items=[{"name": "máy giặt", "category_code": "hazardous", "qty": 1}],
        min_kg=33.0,
        max_kg=77.0,
    )
    truoc = cu_dan.green_points

    pickup_flow.xac_nhan_khoi_luong(db_session, request=yeu_cau, weight_confirmed_kg=55.0, actor=nguoi_can)
    db_session.flush()

    dong = db_session.scalar(select(DiemThuongLog).where(DiemThuongLog.request_id == yeu_cau.id))
    assert dong is not None, "Phải có một dòng sổ cái sau khi hoàn tất"
    assert cu_dan.green_points == truoc + dong.diem
    assert dong.weight_confirmed_kg == 55.0


# --- Hai chuỗi trạng thái chết trong `me_history` --------------------------


def test_history_dem_dung_yeu_cau_hoan_tat(db_session) -> None:
    from src.api.routers.auth import me_history

    cu_dan = _cu_dan(db_session)
    _yeu_cau(
        db_session,
        cu_dan=cu_dan,
        status="hoan_tat",
        weight_confirmed_kg=5.0,
        items=[{"name": "tủ", "category_code": "bulky", "qty": 1}],
    )

    ket_qua = me_history(cu_dan, db_session)

    assert ket_qua["tong"]["so_yeu_cau"] == 1
    assert ket_qua["tong"]["so_yeu_cau_da_thu"] == 1, "Một yêu cầu hoan_tat phải đếm là đã thu"


def test_history_bo_qua_yeu_cau_da_huy_va_tu_choi(db_session) -> None:
    from src.api.routers.auth import me_history

    cu_dan = _cu_dan(db_session)
    _yeu_cau(db_session, cu_dan=cu_dan, status="hoan_tat", weight_confirmed_kg=5.0,
             items=[{"name": "tủ", "category_code": "bulky", "qty": 1}])
    _yeu_cau(db_session, cu_dan=cu_dan, status="da_huy", weight_confirmed_kg=None,
             items=[{"name": "x", "category_code": "bulky", "qty": 1}])
    _yeu_cau(db_session, cu_dan=cu_dan, status="tu_choi", weight_confirmed_kg=None,
             items=[{"name": "y", "category_code": "bulky", "qty": 1}])

    ket_qua = me_history(cu_dan, db_session)

    assert ket_qua["tong"]["so_yeu_cau"] == 1, "da_huy và tu_choi không được đếm vào tổng"
