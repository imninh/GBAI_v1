"""Test chuỗi thời gian xu hướng phân loại & thu gom (GOI_FIX3 / B2)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from scripts.seed import seed_buildings, seed_categories, seed_knowledge, seed_schedules, seed_units, seed_users
from src.api.deps import get_db
from src.config import reset_settings_cache
from src.db.models import Base, Classification, PickupRoute, RouteStop
from src.main import app

MAT_KHAU = "demo1234"


@pytest.fixture(autouse=True)
def _xoam_cache_cau_hinh() -> None:
    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture
def api_session() -> Session:
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


def _ngay_vn(cach_ngay: int) -> datetime:
    """Datetime UTC sao cho VN date (= UTC+7) rơi vào `cach_ngay` ngày trước."""
    hom_nay_vn = (datetime.now() + timedelta(hours=7)).date()
    muc_tieu = hom_nay_vn - timedelta(days=cach_ngay)
    # 12:00 UTC -> 19:00 VN, chắc chắn không vướng biên ngày.
    return datetime(muc_tieu.year, muc_tieu.month, muc_tieu.day, 12, 0, 0)


@pytest.mark.asyncio
async def test_trend_dem_dung_7_ngay(api: AsyncClient, api_session: Session) -> None:
    tuyen = PickupRoute(service_date=date.today())
    api_session.add(tuyen)
    api_session.flush()

    # Phân loại: 3 cái cách 2 ngày, 5 cái cách 4 ngày.
    for _ in range(3):
        api_session.add(Classification(created_at=_ngay_vn(2)))
    for _ in range(5):
        api_session.add(Classification(created_at=_ngay_vn(4)))
    # Thu gom: 2 điểm hoàn thành cách 1 ngày.
    for _ in range(2):
        api_session.add(RouteStop(route_id=tuyen.id, done_at=_ngay_vn(1)))
    api_session.commit()

    token = await _dang_nhap(api, "manager@demo.vn")
    resp = await api.get("/api/v1/insights/trend?days=7", headers=_auth(token))
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 7
    # Thứ tự: cũ -> mới (index 0 = -6 ngày, index 6 = hôm nay).
    assert items[4]["so_phan_loai"] == 3  # cách 2 ngày -> index 4
    assert items[2]["so_phan_loai"] == 5  # cách 4 ngày -> index 2
    assert items[5]["so_thu_gom"] == 2    # cách 1 ngày -> index 5
    # Những ngày còn lại = 0.
    assert items[0]["so_phan_loai"] == 0 and items[0]["so_thu_gom"] == 0
    assert items[6]["so_phan_loai"] == 0 and items[6]["so_thu_gom"] == 0
    # ISO date đúng khuôn.
    hom_nay_vn = (datetime.now() + timedelta(hours=7)).date()
    assert items[0]["date"] == (hom_nay_vn - timedelta(days=6)).isoformat()
    assert items[-1]["date"] == hom_nay_vn.isoformat()


@pytest.mark.asyncio
async def test_trend_ngay_le_xu_ly_an_toan(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "manager@demo.vn")
    # 0 / -5 -> kẹp về 1 ngày; 100 -> kẹp về 90 ngày.
    for bad, expected in ((0, 1), (-5, 1), (100, 90)):
        resp = await api.get(f"/api/v1/insights/trend?days={bad}", headers=_auth(token))
        assert resp.status_code == 200, resp.text
        assert len(resp.json()["items"]) == expected


@pytest.mark.asyncio
async def test_trend_thieu_quyen_thi_403(api: AsyncClient) -> None:
    # Cư dân không có quyền view_ops → 403 (không phải 401 của chưa đăng nhập).
    token = await _dang_nhap(api, "resident@demo.vn")
    resp = await api.get("/api/v1/insights/trend?days=7", headers=_auth(token))
    assert resp.status_code == 403, resp.text
