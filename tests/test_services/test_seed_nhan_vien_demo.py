"""Dữ liệu demo có hai nhân viên vệ sinh để ô "giao thùng cho ai" có nghĩa.

Không dùng fixture API — dựng CSDL SQLite trong bộ nhớ rồi gọi thẳng hàm của
``scripts.seed`` và ``src.db.seed_data``, đúng kiểu ``tests/conftest.py`` làm.
"""

from __future__ import annotations

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from src.db.models import Base, Bin, User
from src.db.seed_data import SEED_GAN_THUNG, USERS, gan_thung_demo, seed_bins
from src.services import bins


def _session_seed_du_lieu() -> Session:
    """CSDL trong bộ nhớ, đã nạp người dùng + 10 thùng demo."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()

    from scripts.seed import seed_users

    seed_users(session, {})
    seed_bins(session)
    session.commit()
    return session


def test_co_dung_hai_nhan_vien_ve_sinh_trong_seed() -> None:
    nhan_vien = [row for row in USERS if row["role"] == "cleaner"]
    assert len(nhan_vien) == 2, "Phải có đúng hai nhân viên vệ sinh trong USERS"
    assert nhan_vien[0]["phone"] != nhan_vien[1]["phone"], "Hai nhân viên phải khác số điện thoại"


def test_ba_tai_khoan_demo_cu_khong_doi() -> None:
    """Ba nút 'vào thẳng' của màn đăng nhập đi qua ba tài khoản này."""
    theo_email = {row["email"]: row for row in USERS}
    assert theo_email["resident@demo.vn"]["phone"] == "0901000001"
    assert theo_email["cleaner@demo.vn"]["phone"] == "0901000002"
    assert theo_email["manager@demo.vn"]["phone"] == "0901000003"
    for email in ("resident@demo.vn", "cleaner@demo.vn", "manager@demo.vn"):
        assert theo_email[email]["role"] == {
            "resident@demo.vn": "resident",
            "cleaner@demo.vn": "cleaner",
            "manager@demo.vn": "manager",
        }[email]


def test_seed_gan_thung_chia_cho_ca_hai_nguoi() -> None:
    moi_ma = [ma for ds in SEED_GAN_THUNG.values() for ma in ds]
    assert len(moi_ma) == 8, "Tổng số thùng được gán phải là 8 (6 + 2)"
    assert len(set(moi_ma)) == 8, "Không mã thùng nào được gán cho hai người"


def test_gan_thung_demo_chia_dung_va_con_thung_chua_gan() -> None:
    session = _session_seed_du_lieu()
    try:
        gan_thung_demo(session)
        session.commit()

        so_thung = {}
        for email in ("cleaner@demo.vn", "cleaner2@demo.vn"):
            nhan_vien = session.scalar(select(User.id).where(User.email == email))
            so_thung[email] = session.scalar(
                select(func.count(Bin.id)).where(Bin.assigned_cleaner_id == nhan_vien)
            )
        assert so_thung["cleaner@demo.vn"] == 6
        assert so_thung["cleaner2@demo.vn"] == 2

        chua_gan = session.scalar(select(func.count(Bin.id)).where(Bin.assigned_cleaner_id.is_(None)))
        assert chua_gan == 2, "Phải còn đúng 2 thùng chưa giao cho ai"
    finally:
        session.close()


def test_danh_sach_nhan_vien_tra_ve_ca_hai_kem_so_thung() -> None:
    session = _session_seed_du_lieu()
    try:
        gan_thung_demo(session)
        session.commit()

        ds = bins.danh_sach_nhan_vien(session)
        assert len(ds) == 2, "Phải trả về đúng hai nhân viên"
        theo_ten = {nv["full_name"]: nv["so_thung_duoc_giao"] for nv in ds}
        assert theo_ten == {"Bùi Thị Mai": 2, "Lê Văn Hùng": 6}
        ten = [nv["full_name"] for nv in ds]
        assert ten == sorted(ten), "Danh sách phải sắp theo full_name"
    finally:
        session.close()
