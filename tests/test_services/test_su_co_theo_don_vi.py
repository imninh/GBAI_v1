"""Gói P83 — sự cố thu gom được lọc theo đơn vị của người xem.

Dựng CSDL SQLite trong bộ nhớ theo đúng khuôn các file test trong
``tests/test_services/``: hai đơn vị, mỗi đơn vị một quản lý + một nhân viên
``cleaner``, mỗi nhân viên được giao một chuyến, mỗi người báo một sự cố — và
thêm vài sự cố để kiểm nhánh IS NULL và sự kết hợp của ba bộ lọc.

Không đụng seed demo (file đó thuộc gói khác) — tự dựng dữ liệu, không phụ
thuộc gì ngoài model.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.models import Base, Organization, PickupRoute, SuCoThuGom, User
from src.services.su_co_thu_gom import danh_sach_su_co


def _build():
    """Dựng bối cảnh: 2 đơn vị, 3 người báo sự cố, 5 sự cố.

    Người xem để test:
      * m0 — quản lý chưa gắn đơn vị (không bị lọc).
      * m1 — quản lý đơn vị 1.  m2 — quản lý đơn vị 2.
      * c0 — cleaner chưa gắn đơn vị.  c1 — cleaner đơn vị 1.  c2 — cleaner đơn vị 2.

    Sự cố:
      * sc1 — c1 (đv1) báo, route r1, ``cho_xu_ly``.
      * sc2 — c2 (đv2) báo, route r2, ``cho_xu_ly``.
      * sc0 — c0 (chưa gắn đơn vị) báo, route r1, ``cho_xu_ly``.
      * sc3 — c1 (đv1) báo, route r2, ``cho_xu_ly`` (khác route với sc1).
      * sc4 — c1 (đv1) báo, route r1, ``da_xu_ly`` (khác trạng thái với sc1).
    """
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, expire_on_commit=False)()

    org1 = Organization(code="ORG1", name="ĐVTG Một")
    org2 = Organization(code="ORG2", name="ĐVTG Hai")
    s.add_all([org1, org2])
    s.flush()

    m0 = User(email="m0@x.vn", full_name="M0", role="manager", password_hash="x")
    m1 = User(email="m1@x.vn", full_name="M1", role="manager", organization_id=org1.id, password_hash="x")
    m2 = User(email="m2@x.vn", full_name="M2", role="manager", organization_id=org2.id, password_hash="x")
    c0 = User(email="c0@x.vn", full_name="C0", role="cleaner", password_hash="x")
    c1 = User(email="c1@x.vn", full_name="C1", role="cleaner", organization_id=org1.id, password_hash="x")
    c2 = User(email="c2@x.vn", full_name="C2", role="cleaner", organization_id=org2.id, password_hash="x")
    s.add_all([m0, m1, m2, c0, c1, c2])
    s.flush()

    r1 = PickupRoute(service_date=date.today(), team_id=c1.id, status="done")
    r2 = PickupRoute(service_date=date.today(), team_id=c2.id, status="done")
    s.add_all([r1, r2])
    s.flush()

    def _su_co(nguoi, route, trang_thai):
        sc = SuCoThuGom(
            route_id=route.id,
            nguoi_bao_id=nguoi.id,
            loai="thung_day",
            mo_ta="",
            trang_thai=trang_thai,
        )
        s.add(sc)
        s.flush()
        return sc

    sc1 = _su_co(c1, r1, "cho_xu_ly")
    sc2 = _su_co(c2, r2, "cho_xu_ly")
    sc0 = _su_co(c0, r1, "cho_xu_ly")
    sc3 = _su_co(c1, r2, "cho_xu_ly")
    sc4 = _su_co(c1, r1, "da_xu_ly")
    s.commit()

    return {
        "s": s,
        "orgs": (org1, org2),
        "users": {"m0": m0, "m1": m1, "m2": m2, "c0": c0, "c1": c1, "c2": c2},
        "routes": (r1, r2),
        "su_co": (sc1, sc2, sc0, sc3, sc4),
    }


def _id_su_co(ket_qua):
    return {sc.id for sc in ket_qua}


def test_quan_ly_don_vi_1_khong_thay_su_co_don_vi_2() -> None:
    b = _build()
    ket_qua = danh_sach_su_co(b["s"], nguoi_xem=b["users"]["m1"])
    cac_id = _id_su_co(ket_qua)
    sc1, sc2, sc0, sc3, sc4 = b["su_co"]
    assert sc2.id not in cac_id, "Quản lý đơn vị 1 không được thấy sự cố của đơn vị 2"
    assert sc1.id in cac_id, "Quản lý đơn vị 1 phải thấy sự cố của đơn vị mình"


def test_quan_ly_don_vi_2_khong_thay_su_co_don_vi_1() -> None:
    b = _build()
    ket_qua = danh_sach_su_co(b["s"], nguoi_xem=b["users"]["m2"])
    cac_id = _id_su_co(ket_qua)
    sc1, sc2, sc0, sc3, sc4 = b["su_co"]
    assert sc1.id not in cac_id, "Quản lý đơn vị 2 không được thấy sự cố của đơn vị 1"
    assert sc2.id in cac_id, "Quản lý đơn vị 2 phải thấy sự cố của đơn vị mình"


def test_quan_ly_van_thay_du_su_co_don_vi_minh() -> None:
    b = _build()
    ket_qua = danh_sach_su_co(b["s"], nguoi_xem=b["users"]["m1"])
    cac_id = _id_su_co(ket_qua)
    sc1, sc2, sc0, sc3, sc4 = b["su_co"]
    assert cac_id == {sc1.id, sc0.id, sc3.id, sc4.id}, (
        "Đếm đúng số sự cố của đơn vị mình (kể cả người chưa gắn đơn vị) — "
        f"nhận được {cac_id}"
    )


def test_nhan_vien_chi_thay_su_co_minh_bao() -> None:
    b = _build()
    ket_qua = danh_sach_su_co(b["s"], nguoi_xem=b["users"]["c1"])
    cac_id = _id_su_co(ket_qua)
    sc1, sc2, sc0, sc3, sc4 = b["su_co"]
    assert cac_id == {sc1.id, sc3.id, sc4.id}, (
        "Cleaner chỉ thấy sự cố mình báo — kể cả trong cùng đơn vị, không thấy "
        f"sự cố của c0 hay c2; nhận được {cac_id}"
    )


def test_nguoi_xem_khong_gan_don_vi_thi_khong_bi_loc() -> None:
    b = _build()
    ket_qua = danh_sach_su_co(b["s"], nguoi_xem=b["users"]["m0"])
    cac_id = _id_su_co(ket_qua)
    sc1, sc2, sc0, sc3, sc4 = b["su_co"]
    assert cac_id == {sc1.id, sc2.id, sc0.id, sc3.id, sc4.id}, (
        "Người xem chưa gắn đơn vị không bị lọc — thấy tất cả; "
        f"nhận được {cac_id}"
    )


def test_su_co_cua_nguoi_chua_gan_don_vi_van_hien() -> None:
    b = _build()
    ket_qua = danh_sach_su_co(b["s"], nguoi_xem=b["users"]["m1"])
    cac_id = _id_su_co(ket_qua)
    sc1, sc2, sc0, sc3, sc4 = b["su_co"]
    assert sc0.id in cac_id, (
        "Nhánh IS NULL: sự cố do người chưa gắn đơn vị báo vẫn hiện với quản lý "
        "có đơn vị — không giấu mất dữ liệu cũ"
    )


def test_loc_don_vi_khong_pha_loc_trang_thai_va_chuyen() -> None:
    b = _build()
    sc1, sc2, sc0, sc3, sc4 = b["su_co"]
    r1 = b["routes"][0]
    ket_qua = danh_sach_su_co(
        b["s"],
        nguoi_xem=b["users"]["m1"],
        trang_thai="cho_xu_ly",
        route_id=r1.id,
    )
    cac_id = _id_su_co(ket_qua)
    assert cac_id == {sc1.id, sc0.id}, (
        "Ba bộ lọc chạy cùng lúc: đơn vị (không có sc2), route (không có sc3), "
        f"trạng thái (không có sc4); nhận được {cac_id}"
    )
