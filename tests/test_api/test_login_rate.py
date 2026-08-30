"""Test giới hạn tần suất đăng nhập (GOI_FIX2 / B6)."""

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
from src.services.gioi_han_tan_suat import dat_lai

MAT_KHAU = "demo1234"


@pytest.fixture(autouse=True)
def _cau_hinh(monkeypatch: pytest.MonkeyPatch) -> None:
    # Giới hạn nhỏ để kích 429 deterministically; dat_lai xoá bộ đếm module.
    monkeypatch.setenv("LOGIN_RATE_LIMIT", "3")
    monkeypatch.setenv("LOGIN_RATE_WINDOW_SECONDS", "300")
    reset_settings_cache()
    dat_lai()
    yield
    dat_lai()
    reset_settings_cache()


@pytest.fixture
def api_session(monkeypatch: pytest.MonkeyPatch) -> Session:
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


@pytest.mark.asyncio
async def test_dang_nhap_qua_gioi_han_thi_429(api: AsyncClient) -> None:
    # 3 lần đầu được phép (thành công hay sai mật khẩu đều tính), lần 4 → 429.
    ma = {"email": "manager@demo.vn", "password": MAT_KHAU}
    for _ in range(3):
        r = await api.post("/api/v1/auth/login", json=ma)
        assert r.status_code in (200, 401), r.text
    rot = await api.post("/api/v1/auth/login", json=ma)
    assert rot.status_code == 429, rot.text
    assert rot.json()["error"]["code"] == "RATE-429"
