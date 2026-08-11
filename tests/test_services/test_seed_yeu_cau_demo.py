"""Dữ liệu demo có đúng một yêu cầu đang chờ xác nhận khối lượng (gói P14).

Yêu cầu đó nuôi hàng đợi "Chờ xác nhận khối lượng" trên web đơn vị thu gom và
cho ``scripts/chuan_bi_demo.py --lam`` có việc để làm. Không dùng fixture API —
dựng CSDL SQLite trong bộ nhớ rồi gọi thẳng hàm của ``scripts.seed``, đúng kiểu
``tests/test_services/test_seed_nhan_vien_demo.py`` làm.
"""

from __future__ import annotations

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from src.db.models import Base, PickupRequest, User
from src.services.pickup_lifecycle import (
    CHO_DUYET,
    CHO_NHAN,
    CHUYEN_TIEP,
    DA_GIAO_DON_VI,
)

_TU_VUNG_CU = {"pending", "approved", "scheduled", "done", "cancelled", "rejected"}


def _session_seed_du_lieu() -> Session:
    """CSDL trong bộ nhớ, đã nạp dữ liệu nền + các yêu cầu demo."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()

    from scripts.seed import seed_buildings, seed_categories, seed_demo_pickups, seed_units, seed_users

    seed_categories(session)
    toa_nha = seed_buildings(session)
    can_ho = seed_units(session, toa_nha)
    seed_users(session, can_ho)
    seed_demo_pickups(session)
    session.commit()
    return session


def _dem_theo_trang_thai(session: Session) -> dict[str, int]:
    return dict(session.execute(select(PickupRequest.status, func.count(PickupRequest.id)).group_by(PickupRequest.status)).all())


def test_co_dung_mot_yeu_cau_cho_xac_nhan_khoi_luong() -> None:
    session = _session_seed_du_lieu()
    try:
        so = session.scalar(select(func.count(PickupRequest.id)).where(PickupRequest.status == DA_GIAO_DON_VI))
        assert so == 1, "Phải có đúng một yêu cầu ở da_giao_don_vi để nuôi hàng đợi xác nhận khối lượng"
    finally:
        session.close()


def test_yeu_cau_do_thuoc_cu_dan_demo() -> None:
    session = _session_seed_du_lieu()
    try:
        yeu_cau = session.scalar(select(PickupRequest).where(PickupRequest.status == DA_GIAO_DON_VI))
        assert yeu_cau is not None
        cu_dan = session.get(User, yeu_cau.resident_id)
        assert cu_dan is not None
        assert cu_dan.email == "resident@demo.vn"
        assert yeu_cau.is_seed is True, "Bản ghi demo phải gắn cờ is_seed để UI dán nhãn"
        assert yeu_cau.weight_min_kg is not None
        assert yeu_cau.weight_max_kg is not None
    finally:
        session.close()


def test_van_con_yeu_cau_cho_duyet_va_cho_nhan() -> None:
    """Hàng đợi duyệt của quản lý không được nghèo đi vì gói này."""
    session = _session_seed_du_lieu()
    try:
        dem = _dem_theo_trang_thai(session)
        assert dem.get(CHO_DUYET) == 2, "Phải còn đúng 2 yêu cầu chờ duyệt như trước gói"
        assert dem.get(CHO_NHAN) == 4, "Phải còn đúng 4 yêu cầu chờ nhận như trước gói"
    finally:
        session.close()


def test_chay_seed_lan_hai_khong_nhan_doi_yeu_cau() -> None:
    """Seed đầy đủ (``bootstrap demo``) chạy hai lần không nhân đôi yêu cầu."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()

    from scripts.seed import bootstrap

    try:
        bootstrap(session, demo=True)
        bootstrap(session, demo=True)
        session.commit()
        so = session.scalar(select(func.count(PickupRequest.id)).where(PickupRequest.status == DA_GIAO_DON_VI))
        assert so == 1, "Chạy seed lần hai không được sinh thêm yêu cầu da_giao_don_vi"
    finally:
        session.close()


def test_trang_thai_nam_trong_tu_vung_moi() -> None:
    session = _session_seed_du_lieu()
    try:
        cac_trang_thai = session.scalars(select(PickupRequest.status)).all()
        assert cac_trang_thai
        for trang_thai in cac_trang_thai:
            assert trang_thai in CHUYEN_TIEP, f"'{trang_thai}' không nằm trong 10 trạng thái mới"
            assert trang_thai not in _TU_VUNG_CU, f"'{trang_thai}' là từ vựng cũ, phải di trú"
    finally:
        session.close()
