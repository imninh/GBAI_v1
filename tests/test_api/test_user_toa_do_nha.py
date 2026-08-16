"""Test API người dùng — phải trả toạ độ toà nhà đăng ký để sắp theo khoảng cách."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.deps import get_db
from src.config import reset_settings_cache
from src.db.models import Base, Building, Unit, User
from src.main import app
from src.services.security import hash_password

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

    # StaticPool là bắt buộc: FastAPI chạy endpoint đồng bộ ở threadpool, mà
    # SQLite in-memory mặc định cấp cho mỗi thread một CSDL rỗng riêng.
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


async def _dang_nhap(api: AsyncClient, email: str) -> dict:
    response = await api.post("/api/v1/auth/login", json={"email": email, "password": MAT_KHAU})
    assert response.status_code == 200, response.text
    return response.json()["user"]


# --- Toạ độ toà nhà đăng ký -----------------------------------------------


@pytest.mark.asyncio
async def test_toa_do_toa_nha_dang_ky_tra_ve_dung(api: AsyncClient, api_session: Session) -> None:
    """Cư dân có căn hộ thì API phải trả đúng toạ độ toà nhà họ đang ở."""
    cu_dan = api_session.scalar(select(User).where(User.email == "resident@demo.vn"))
    assert cu_dan is not None and cu_dan.unit_id is not None
    toa = api_session.get(Building, api_session.get(Unit, cu_dan.unit_id).building_id)
    assert toa is not None and toa.lat is not None and toa.lng is not None

    user = await _dang_nhap(api, "resident@demo.vn")

    assert user["building_lat"] == toa.lat
    assert user["building_lng"] == toa.lng


@pytest.mark.asyncio
async def test_chua_gan_can_ho_thi_khong_co_toa_do(api: AsyncClient, api_session: Session) -> None:
    """Người chưa gắn căn hộ phải nhận `None`, không phải `0.0` và không nổ."""
    api_session.add(
        User(
            email="khong-nha@test.vn",
            full_name="Người chưa gắn nhà",
            role="resident",
            password_hash=hash_password(MAT_KHAU),
        )
    )
    api_session.commit()

    user = await _dang_nhap(api, "khong-nha@test.vn")

    assert user["building_lat"] is None
    assert user["building_lng"] is None
