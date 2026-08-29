"""Test API lịch thu gom — PUT sửa lịch của toà (GOI_P3 / B1)."""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.deps import get_db
from src.config import reset_settings_cache
from src.db.models import Base
from src.main import app

MAT_KHAU = "demo1234"


@pytest.fixture(autouse=True)
def _xoam_cache_cau_hinh() -> None:
    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture
def api_session(monkeypatch: pytest.MonkeyPatch) -> Session:
    from scripts.seed import (
        seed_buildings,
        seed_categories,
        seed_knowledge,
        seed_schedules,
        seed_units,
        seed_users,
    )

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    seed_categories(session)
    buildings = seed_buildings(session)
    units = seed_units(session, buildings)
    seed_users(session, units)
    seed_schedules(session, buildings)
    seed_knowledge(session, buildings)
    session.commit()

    def _override() -> Session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

    app.dependency_overrides[get_db] = _override
    try:
        yield session
    finally:
        app.dependency_overrides.clear()
        session.close()
        engine.dispose()


@pytest_asyncio.fixture
async def api(api_session: Session) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _dang_nhap(api: AsyncClient, email: str) -> str:
    response = await api.post("/api/v1/auth/login", json={"email": email, "password": MAT_KHAU})
    assert response.status_code == 200, response.text
    return response.json()["token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _lay_toa_va_category(api: AsyncClient, token: str):
    b = await api.get("/api/v1/buildings", headers=_auth(token))
    assert b.status_code == 200, b.text
    building_id = b.json()["items"][0]["id"]
    c = await api.get("/api/v1/categories", headers=_auth(token))
    assert c.status_code == 200, c.text
    cat = c.json()["items"][0]["code"]
    return building_id, cat


@pytest.mark.asyncio
async def test_put_schedule_roi_get_dung(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "manager@demo.vn")
    building_id, cat = await _lay_toa_va_category(api, token)
    body = {
        "items": [
            {"category_code": cat, "weekdays": [0, 2, 4], "window": "18:00-20:00", "location": "Sảnh B"}
        ]
    }
    r = await api.put(f"/api/v1/buildings/{building_id}/schedule", headers=_auth(token), json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["items"][0]["weekdays"] == [0, 2, 4]
    assert data["items"][0]["window"] == "18:00-20:00"

    # GET lại thấy đổi (thay thế toàn bộ hàng cũ).
    g = await api.get(f"/api/v1/buildings/{building_id}/schedule", headers=_auth(token))
    assert g.status_code == 200, g.text
    items = g.json()["items"]
    assert len(items) == 1
    assert items[0]["weekdays"] == [0, 2, 4]
    assert items[0]["location"] == "Sảnh B"


@pytest.mark.asyncio
async def test_put_schedule_weekdays_khong_hop_le(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "manager@demo.vn")
    building_id, cat = await _lay_toa_va_category(api, token)

    r = await api.put(
        f"/api/v1/buildings/{building_id}/schedule",
        headers=_auth(token),
        json={"items": [{"category_code": cat, "weekdays": [9]}]},
    )
    assert r.status_code == 400, r.text

    r2 = await api.put(
        f"/api/v1/buildings/{building_id}/schedule",
        headers=_auth(token),
        json={"items": [{"category_code": "khong_ton_tai", "weekdays": [0]}]},
    )
    assert r2.status_code == 400, r2.text

    r3 = await api.put(
        f"/api/v1/buildings/{building_id}/schedule",
        headers=_auth(token),
        json={"items": [{"category_code": cat, "weekdays": [0], "window": "sai_dinh_dang"}]},
    )
    assert r3.status_code == 400, r3.text


@pytest.mark.asyncio
async def test_put_schedule_het_quyen_resident(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "resident@demo.vn")
    building_id, cat = await _lay_toa_va_category(api, token)
    r = await api.put(
        f"/api/v1/buildings/{building_id}/schedule",
        headers=_auth(token),
        json={"items": [{"category_code": cat, "weekdays": [0]}]},
    )
    assert r.status_code == 403, r.text
