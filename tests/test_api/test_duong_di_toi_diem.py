"""Endpoint ``POST /routes/duong-di`` — vẽ đường đi thật cho màn Điểm gửi rác.

Cư dân chọn một điểm gửi rác và hệ thống vẽ đường bám phố tới đó (OSRM). Nội
dung hình dạng nằm ở ``duong_di_that.hinh_duong_di`` — module này đã có test
riêng, endpoint ở đây chỉ là proxy: lọc toạ độ, gọi dịch vụ, trả nguyên kết quả.
"""

from __future__ import annotations

from collections.abc import Iterator

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
from src.services import duong_di_that

MAT_KHAU = "demo1234"


@pytest.fixture(autouse=True)
def _xoam_cache_cau_hinh() -> Iterator[None]:
    """Cấu hình đọc qua ``lru_cache`` nên phải xoá cache quanh mỗi test."""
    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture
def api_session(monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    """CSDL trong bộ nhớ đã seed dữ liệu nền, gắn vào dependency của app."""
    from scripts.seed import seed_buildings, seed_categories, seed_knowledge, seed_schedules, seed_units, seed_users

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

    def _override() -> Iterator[Session]:
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


async def _auth_cu_dan(api: AsyncClient) -> dict[str, str]:
    response = await api.post("/api/v1/auth/login", json={"email": "resident@demo.vn", "password": MAT_KHAU})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.mark.asyncio
async def test_duoi_hai_diem_thi_tra_null(api: AsyncClient, api_session: Session) -> None:
    """Một điểm (hoặc điểm bị thiếu toạ độ) không vẽ được đường đi thật."""
    auth = await _auth_cu_dan(api)

    for diem in ([], [{"lat": 21.0, "lng": 105.8}], [{"lng": 105.8}]):
        response = await api.post("/api/v1/routes/duong-di", json={"diem": diem}, headers=auth)
        assert response.status_code == 200, response.text
        assert response.json()["duong_di"] is None


@pytest.mark.asyncio
async def test_osrm_tat_mac_dinh_thi_tra_null(api: AsyncClient, api_session: Session) -> None:
    """Cờ ``ROUTE_REAL_DISTANCE`` tắt (mặc định) → endpoint trả null, không gọi mạng."""
    auth = await _auth_cu_dan(api)

    response = await api.post(
        "/api/v1/routes/duong-di",
        json={"diem": [{"lat": 21.0, "lng": 105.8}, {"lat": 21.1, "lng": 105.9}]},
        headers=auth,
    )

    assert response.status_code == 200, response.text
    assert response.json()["duong_di"] is None


@pytest.mark.asyncio
async def test_hinh_duong_di_duoc_tra_nguyen_ven(
    api: AsyncClient, api_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OSRM trả hình dạng thì endpoint chuyển tiếp nguyên vẹn cho client."""
    monkeypatch.setattr(
        duong_di_that,
        "hinh_duong_di",
        lambda toa_do: [(21.0, 105.8), (21.1, 105.9)],
    )
    auth = await _auth_cu_dan(api)

    response = await api.post(
        "/api/v1/routes/duong-di",
        json={"diem": [{"lat": 21.0, "lng": 105.8}, {"lat": 21.1, "lng": 105.9}]},
        headers=auth,
    )

    assert response.status_code == 200, response.text
    assert response.json()["duong_di"] == [[21.0, 105.8], [21.1, 105.9]]
