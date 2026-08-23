"""Gói A1 — nền dữ liệu cho đơn vị thu gom: bảng ``organizations`` và cột
``organization_id`` trên ``users`` / ``bins``.

Gói này CỐ TÌNH chưa lọc gì theo tổ chức — chỉ đặt nền dữ liệu. Việc tách dữ
liệu giữa các đơn vị là gói A1b (test số 7 ghim ngầm ranh giới đó).

Không dùng fixture API — dựng CSDL SQLite trong bộ nhớ rồi gọi thẳng hàm của
``src.db.seed_data``, đúng kiểu ``tests/conftest.py`` làm.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from src.db.models import Base, Bin, Organization, User
from src.db.schema_patch import COT_CAN_VA
from src.db.seed_data import seed_bins, to_chuc_demo

_THU_MUC_GHI = (Path(__file__).resolve().parents[2] / "src") / "services"
_THU_MUC_API = (Path(__file__).resolve().parents[2] / "src") / "api"


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


def test_tao_to_chuc_mot_lan() -> None:
    session = _session_seed_du_lieu()
    try:
        to_chuc_demo(session)
        to_chuc_demo(session)
        session.commit()
        so_to_chuc = session.scalar(select(func.count(Organization.id)))
        assert so_to_chuc == 1, "Chạy hai lần phải chỉ tạo đúng một đơn vị"
    finally:
        session.close()


def test_gan_to_chuc_cho_nhan_vien_va_quan_ly() -> None:
    session = _session_seed_du_lieu()
    try:
        to_chuc_demo(session)
        session.commit()
        nhan_su = session.scalars(select(User).where(User.role.in_(["cleaner", "manager"]))).all()
        assert nhan_su, "Phải có nhân viên và quản lý trong dữ liệu seed"
        for nguoi in nhan_su:
            assert nguoi.organization_id is not None, f"{nguoi.email} phải được gắn tổ chức"
    finally:
        session.close()


def test_khong_gan_to_chuc_cho_cu_dan() -> None:
    session = _session_seed_du_lieu()
    try:
        to_chuc_demo(session)
        session.commit()
        cu_dan = session.scalars(select(User).where(User.role == "resident")).all()
        assert cu_dan, "Phải có cư dân trong dữ liệu seed"
        for nguoi in cu_dan:
            assert nguoi.organization_id is None, "Cư dân KHÔNG thuộc đơn vị thu gom nào"
    finally:
        session.close()


def test_gan_to_chuc_cho_moi_thung() -> None:
    session = _session_seed_du_lieu()
    try:
        to_chuc_demo(session)
        session.commit()
        thung = session.scalars(select(Bin)).all()
        assert thung, "Phải có thùng trong dữ liệu seed"
        for mot_thung in thung:
            assert mot_thung.organization_id is not None, "Mọi thùng phải được gắn tổ chức"
    finally:
        session.close()


def test_khong_ghi_de_gia_tri_da_co() -> None:
    session = _session_seed_du_lieu()
    try:
        to_chuc_demo(session)
        session.commit()
        nhan_vien = session.scalar(select(User).where(User.role == "cleaner"))
        assert nhan_vien is not None
        nhan_vien.organization_id = 999
        session.commit()

        to_chuc_demo(session)
        session.commit()
        session.refresh(nhan_vien)
        assert nhan_vien.organization_id == 999, "Seed lại không được ghi đè giá trị đã có"
    finally:
        session.close()


def test_hai_cot_duoc_khai_trong_cot_can_va() -> None:
    """Chốt chặn cái bẫy hạ tầng: cột thêm vào bảng đã có mà quên khai
    ``COT_CAN_VA`` thì test vẫn xanh nhưng CSDL thật thiếu cột."""
    cap_bang_cot = {(bang, ten_cot) for bang, ten_cot, _ in COT_CAN_VA}
    assert ("users", "organization_id") in cap_bang_cot
    assert ("bins", "organization_id") in cap_bang_cot


def test_loc_theo_to_chuc_chi_nam_trong_hai_file() -> None:
    """Bộ lọc tổ chức chỉ được nằm trong ĐÚNG HAI file quy định.

    Gói P83 tách phạm vi đơn vị ra module riêng (``pham_vi_to_chuc``) để mọi
    thực thể đều hỏi một chỗ duy nhất, thay vì giam chữ ``organization_id`` trong
    mỗi module quản lý thùng. Nơi quyết định phạm vi bây giờ là ĐÚNG HAI file:
    ``bins.py`` (phạm vi nhân viên + các mệnh đề thùng) và
    ``pham_vi_to_chuc.py`` (phạm vi đơn vị).

    So sánh BẰNG ĐÚNG danh sách — không dùng ``issubset`` hay ``in``: thêm file
    thứ ba chứa ``organization_id`` là phải bàn lại (mở rộng quy ước), không phải
    cứ nới test cho xanh. Router vẫn chỉ được hỏi service rồi truyền tiếp.
    """
    cac_tep = sorted(_THU_MUC_GHI.glob("*.py")) + sorted(_THU_MUC_API.rglob("*.py"))
    tep_chua_bien = [
        tep.relative_to(Path(__file__).resolve().parents[2]) for tep in cac_tep if "organization_id" in tep.read_text(encoding="utf-8")
    ]
    assert tep_chua_bien == [
        Path("src/services/bins.py"),
        Path("src/services/pham_vi_to_chuc.py"),
    ], (
        "organization_id phải chỉ xuất hiện trong đúng hai file "
        "src/services/bins.py và src/services/pham_vi_to_chuc.py — "
        f"còn xuất hiện ở: {tep_chua_bien}"
    )
