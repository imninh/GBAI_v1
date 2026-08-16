"""Kiểm thử seed thùng thu gom demo và hàm mô phỏng thiết bị.

Không test nào đụng mạng: phần gửi reading của bộ mô phỏng là vỏ I/O mỏng,
phần đáng test (quy luật tăng/giảm của thùng) nằm trong hàm thuần
:func:`buoc_tiep_theo`; phần seed chạy thẳng trên CSDL trong bộ nhớ.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from scripts.device_simulator import buoc_tiep_theo
from scripts.seed import bootstrap
from src.db.models import Bin
from src.db.seed_data import SEED_BINS, seed_bins
from src.services.bins import trang_thai_thung

# --- Seed thùng demo -------------------------------------------------------


def test_seed_tao_du_thung_va_deu_is_seed(db_session: Session) -> None:
    dem = seed_bins(db_session)
    db_session.commit()

    assert dem == len(SEED_BINS)
    thung = db_session.scalars(select(Bin)).all()
    assert len(thung) == len(SEED_BINS)
    assert all(t.is_seed for t in thung)


def test_seed_chay_hai_lan_khong_sinh_trung(db_session: Session) -> None:
    seed_bins(db_session)
    seed_bins(db_session)
    db_session.commit()

    assert len(db_session.scalars(select(Bin)).all()) == len(SEED_BINS)


def test_seed_co_du_bon_trang_thai(db_session: Session) -> None:
    """Một bộ demo mà mọi thùng giống nhau chẳng chứng minh được gì trên màn
    hình và còn giấu lỗi logic trạng thái — phải đủ cả bốn trạng thái."""
    seed_bins(db_session)
    db_session.commit()
    now = datetime.now(UTC)

    cac_trang_thai = {trang_thai_thung(thung, now) for thung in db_session.scalars(select(Bin)).all()}

    assert cac_trang_thai == {"binh_thuong", "can_gom", "mat_ket_noi", "het_pin"}


# --- Hàm thuần của bộ mô phỏng --------------------------------------------


def test_buoc_tiep_theo_gio_ca_hai_gia_tri_trong_0_100() -> None:
    random.seed(20260806)
    fill, battery = 50.0, 50.0
    for _ in range(300):
        fill, battery = buoc_tiep_theo(fill, battery)
        assert 0 <= fill <= 100
        assert 0 <= battery <= 100


def test_buoc_tiep_theo_reset_ve_muc_thap_sau_khi_vuot_95() -> None:
    random.seed(20260806)
    # Từ đúng 95, bước tiếp theo luôn cộng ít nhất 1 → chắc chắn vượt 95 → reset.
    fill_moi, battery_moi = buoc_tiep_theo(95.0, 60.0)

    assert fill_moi < 20.0, "Vượt 95 là thùng vừa được đổ — phải reset về mức thấp"
    assert 0 <= fill_moi <= 100


def test_buoc_tiep_theo_khong_bao_gio_tang_pin() -> None:
    random.seed(20260806)
    pin = 60.0
    for _ in range(300):
        _, pin_moi = buoc_tiep_theo(50.0, pin)
        assert pin_moi <= pin, "Pin chỉ tụt, không bao giờ tăng"
        pin = pin_moi


# --- Đi qua bootstrap -------------------------------------------------------


def test_bootstrap_demo_tao_du_thung(db_session: Session) -> None:
    """Chạy bootstrap với demo phải tạo đủ số thùng theo SEED_BINS."""
    bootstrap(db_session, demo=True)
    db_session.commit()

    assert len(db_session.scalars(select(Bin)).all()) == len(SEED_BINS)


def test_bootstrap_khong_demo_khong_tao_thung(db_session: Session) -> None:
    """Chạy bootstrap không demo không được sinh thùng nào."""
    bootstrap(db_session, demo=False)
    db_session.commit()

    assert len(db_session.scalars(select(Bin)).all()) == 0


def test_bootstrap_demo_chay_hai_lan_khong_sinh_trung(db_session: Session) -> None:
    """Bootstrap demo chạy hai lần phải vẫn còn đúng số thùng, không trùng."""
    bootstrap(db_session, demo=True)
    bootstrap(db_session, demo=True)
    db_session.commit()

    assert len(db_session.scalars(select(Bin)).all()) == len(SEED_BINS)
