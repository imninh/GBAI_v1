"""Test script backfill users.building_id <- unit_id (local-first, idempotent)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from scripts.backfill_building_id import backfill
from src.db.models import Building, Unit, User


def _tao_toa_va_can(db_session: Session) -> tuple[Building, Unit]:
    toa = Building(code="BF-1", name="Toà backfill", address="1 A", lat=1.0, lng=2.0)
    db_session.add(toa)
    db_session.flush()
    can = Unit(building_id=toa.id, code="BF-01")
    db_session.add(can)
    db_session.flush()
    return toa, can


def test_backfill_chi_unit_id_keo_theo_toa(db_session: Session) -> None:
    toa, can = _tao_toa_va_can(db_session)
    user = User(
        email="bf1@test.vn",
        full_name="Có căn chưa toà",
        role="resident",
        password_hash="x",
        unit_id=can.id,
        building_id=None,
    )
    db_session.add(user)
    db_session.flush()

    # Dry-run: chưa ghi, nhưng nhận diện đúng 1 user cần cập nhật.
    ke_dry = backfill(db_session, dry_run=True)
    assert ke_dry["updated"] == [user.id]
    db_session.expire_all()
    assert db_session.get(User, user.id).building_id is None

    # Apply: ghi thật.
    backfill(db_session, dry_run=False)
    db_session.commit()
    db_session.expire_all()
    assert db_session.get(User, user.id).building_id == toa.id


def test_backfill_khong_dong_toi_user_khong_co_unit(db_session: Session) -> None:
    """606 user không có unit_id tuyệt đối không bị động tới."""
    toa, can = _tao_toa_va_can(db_session)
    user_khong_unit = User(
        email="bf2@test.vn",
        full_name="Không căn",
        role="resident",
        password_hash="x",
        unit_id=None,
        building_id=None,
    )
    db_session.add(user_khong_unit)
    db_session.flush()

    ke = backfill(db_session, dry_run=False)
    db_session.commit()
    db_session.expire_all()
    assert ke["updated"] == []
    assert db_session.get(User, user_khong_unit.id).building_id is None


def test_backfill_cap_moi_khong_ghi_de_ky_tu_mau_thuan(db_session: Session) -> None:
    """User đã có building_id khác với toà của căn hộ → báo conflict, không ghi đè."""
    toa_a, can_a = _tao_toa_va_can(db_session)
    toa_b = Building(code="BF-2", name="Toà B", address="2 B", lat=3.0, lng=4.0)
    db_session.add(toa_b)
    db_session.flush()
    user = User(
        email="bf3@test.vn",
        full_name="Mâu thuẫn",
        role="resident",
        password_hash="x",
        unit_id=can_a.id,
        building_id=toa_b.id,
    )
    db_session.add(user)
    db_session.flush()

    ke = backfill(db_session, dry_run=False)
    db_session.commit()
    db_session.expire_all()
    assert ke["conflict"] == [user.id]
    # Giữ nguyên building_id cũ, không bị ghi đè bằng toà của căn hộ.
    assert db_session.get(User, user.id).building_id == toa_b.id


def test_backfill_da_khop_thi_skip(db_session: Session) -> None:
    toa, can = _tao_toa_va_can(db_session)
    user = User(
        email="bf4@test.vn",
        full_name="Đã khớp",
        role="resident",
        password_hash="x",
        unit_id=can.id,
        building_id=toa.id,
    )
    db_session.add(user)
    db_session.flush()

    ke = backfill(db_session, dry_run=False)
    db_session.commit()
    assert ke["skipped"] == [user.id]
    assert ke["updated"] == []
