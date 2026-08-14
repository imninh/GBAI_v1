"""Gói P45b — chặn yêu cầu thu gom có ``est_weight_kg <= 0`` mà không có khoảng hợp lệ.

Bug backend #7: ``est_weight_kg = 0`` (mặc định) và không gửi khoảng min/max →
``weight_range_from_estimate`` trả khoảng ``(0, 0)`` → đội vệ sinh cân thật (bất kỳ
số > 0) thì yêu cầu LUÔN thành ``tranh_chap``, không bao giờ ``hoan_tat``. Guard này
chặn ngay lúc tạo: vừa không có khoảng hợp lệ VỪA est <= 0 thì raise ``ValueError``.

Không test nào gọi model/mạng thật. Không sửa ``weight_range_from_estimate``,
``evaluate_thresholds``, máy trạng thái, hay router API.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from src.db.models import Building, Unit, User
from src.services import pickup


@pytest.fixture
def cu_dan(db_session: Session) -> User:
    """Một cư dân đã gắn với căn hộ (đủ điều kiện tạo yêu cầu)."""
    toa = Building(code="P45B", name="Toà P45b", lat=10.7769, lng=106.7009)
    db_session.add(toa)
    db_session.flush()
    unit = Unit(building_id=toa.id, code="P45B-01")
    db_session.add(unit)
    db_session.flush()
    cu_dan = User(
        email="cu-dan-p45b@demo.vn",
        full_name="Cư dân P45b",
        role="resident",
        password_hash="x",
        unit_id=unit.id,
    )
    db_session.add(cu_dan)
    db_session.flush()
    return cu_dan


def test_est_0_bi_chan(db_session: Session, cu_dan: User) -> None:
    """``est_weight_kg=0`` và không có khoảng min/max → raise ``ValueError``."""
    with pytest.raises(ValueError, match="khối lượng ước tính"):
        pickup.create_pickup_request(db_session, resident=cu_dan, items=[], est_weight_kg=0)


def test_est_duong_tao_duoc(db_session: Session, cu_dan: User) -> None:
    """``est_weight_kg=5.0`` → tạo được yêu cầu với cận trên > 0."""
    yeu_cau = pickup.create_pickup_request(
        db_session,
        resident=cu_dan,
        items=[{"name": "Bàn", "category_code": "bulky", "qty": 1, "est_weight_kg": 5}],
        est_weight_kg=5.0,
    )

    assert yeu_cau.weight_max_kg > 0
    assert yeu_cau.weight_min_kg > 0


def test_khoang_ro_est_0_khong_bi_chan(db_session: Session, cu_dan: User) -> None:
    """Có khoảng min/max hợp lệ (3–8 kg) thì ``est=0`` vẫn cho qua — không chặn oan."""
    yeu_cau = pickup.create_pickup_request(
        db_session,
        resident=cu_dan,
        items=[],
        est_weight_kg=0,
        weight_min_kg=3,
        weight_max_kg=8,
    )

    assert yeu_cau.weight_min_kg == 3
    assert yeu_cau.weight_max_kg == 8
