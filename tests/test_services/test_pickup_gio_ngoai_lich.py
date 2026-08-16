"""Gói P51 — giờ ngoài lịch (``ngoai_lich=true``) thì cũng cần BQL duyệt.

Khớp quyết định #6: khung giờ trong lịch của toà = đường nhanh (không cần duyệt
giờ), giờ tự chọn ngoài lịch = BQL gật trước. Cờ do frontend gửi (wizard biết
cư dân chọn loại nào); backend mặc định ``False`` nếu thiếu nên mọi lời gọi cũ
không đổi hành vi. Đây là cổng HITL #1 — ``requires_hitl``/``status`` đã khoá
theo ``bool(hits)``, thêm một hit là tự vào ``CHO_DUYET``.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from src.db.models import Building, Unit, User
from src.services import pickup
from src.services.pickup_lifecycle import CHO_DUYET, CHO_NHAN


@pytest.fixture
def cu_dan(db_session: Session) -> User:
    """Một cư dân đã gắn với căn hộ (đủ điều kiện tạo yêu cầu)."""
    toa = Building(code="P51", name="Toà P51", lat=10.7769, lng=106.7009)
    db_session.add(toa)
    db_session.flush()
    unit = Unit(building_id=toa.id, code="P51-01")
    db_session.add(unit)
    db_session.flush()
    cu_dan = User(
        email="cu-dan-p51@demo.vn",
        full_name="Cư dân P51",
        role="resident",
        password_hash="x",
        unit_id=unit.id,
    )
    db_session.add(cu_dan)
    db_session.flush()
    return cu_dan


_MON = {"name": "Tủ nhỏ", "category_code": "bulky", "qty": 1, "est_weight_kg": 8}


def test_gio_ngoai_lich_thi_cho_duyet(db_session: Session, cu_dan: User) -> None:
    """``ngoai_lich=True`` kèm giờ cụ thể → cần BQL duyệt dù khối lượng nhỏ."""
    yeu_cau = pickup.create_pickup_request(
        db_session,
        resident=cu_dan,
        items=[_MON],
        est_weight_kg=8.0,
        preferred_window="20:00-22:00",
        ngoai_lich=True,
    )

    assert yeu_cau.status == CHO_DUYET
    assert yeu_cau.requires_hitl is True
    cac_rule = [h["rule"] for h in yeu_cau.threshold_hit]
    assert "gio_ngoai_lich" in cac_rule
    hit = next(h for h in yeu_cau.threshold_hit if h["rule"] == "gio_ngoai_lich")
    assert "ngoài lịch" in hit["label_vi"]


def test_khong_ngoai_lich_thi_cho_nhan(db_session: Session, cu_dan: User) -> None:
    """``ngoai_lich=False`` cùng dữ liệu → không có hit đó, vẫn trong ngưỡng tự động."""
    yeu_cau = pickup.create_pickup_request(
        db_session,
        resident=cu_dan,
        items=[_MON],
        est_weight_kg=8.0,
        preferred_window="20:00-22:00",
        ngoai_lich=False,
    )

    assert yeu_cau.status == CHO_NHAN
    assert yeu_cau.requires_hitl is False
    cac_rule = [h["rule"] for h in yeu_cau.threshold_hit]
    assert "gio_ngoai_lich" not in cac_rule
