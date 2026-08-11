"""Test khối `co_che` trên trang Vận hành — ba cơ chế mới phải nói thật.

Không test nào gọi API model thật — toàn bộ đi qua ASGITransport trên CSDL
trong bộ nhớ, đúng kiểu các file test API khác trong thư mục này.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from scripts.seed import seed_buildings, seed_categories, seed_knowledge, seed_schedules, seed_units, seed_users
from src.api.deps import get_db
from src.config import reset_settings_cache
from src.db.models import Base, Bin
from src.main import app

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


async def _dang_nhap(api: AsyncClient, email: str) -> str:
    response = await api.post("/api/v1/auth/login", json={"email": email, "password": MAT_KHAU})
    assert response.status_code == 200, response.text
    return response.json()["token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _overview(api: AsyncClient) -> dict:
    token = await _dang_nhap(api, "manager@demo.vn")
    response = await api.get("/api/v1/overview", headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_overview_tra_ve_khoi_co_che(api: AsyncClient) -> None:
    data = await _overview(api)

    assert set(data["co_che"].keys()) == {"rate_limit_dang_ky", "khoa_thiet_bi", "duong_di_that"}
    assert "bat" in data["co_che"]["rate_limit_dang_ky"]
    assert {"so_thung_khoa_rieng", "tong_thung"} <= set(data["co_che"]["khoa_thiet_bi"].keys())
    assert "bat" in data["co_che"]["duong_di_that"]


@pytest.mark.asyncio
async def test_rate_limit_bang_khong_thi_bao_dang_tat(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REGISTER_RATE_LIMIT", "0")
    reset_settings_cache()

    data = await _overview(api)

    assert data["co_che"]["rate_limit_dang_ky"]["bat"] is False


@pytest.mark.asyncio
async def test_dem_dung_so_thung_co_khoa_rieng(api: AsyncClient, api_session: Session) -> None:
    """Chốt chặn cái bẫy `DEFAULT ''`: 2 trong 5 thùng có khoá riêng → đếm ra 2, không phải 5."""
    for code, khoa in (
        ("BIN-A", "khoa-a"),
        ("BIN-B", "khoa-b"),
        ("BIN-C", ""),
        ("BIN-D", ""),
        ("BIN-E", ""),
    ):
        api_session.add(Bin(code=code, name=f"Thùng {code}", device_key_hash=khoa, is_active=True))
    api_session.commit()

    data = await _overview(api)

    assert data["co_che"]["khoa_thiet_bi"]["so_thung_khoa_rieng"] == 2
    assert data["co_che"]["khoa_thiet_bi"]["tong_thung"] == 5


@pytest.mark.asyncio
async def test_duong_di_that_mac_dinh_tat(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Chốt chặn lỗi cố ý: không đặt biến môi trường → cờ thật phải là TẮT."""
    monkeypatch.delenv("ROUTE_REAL_DISTANCE", raising=False)
    reset_settings_cache()

    data = await _overview(api)

    assert data["co_che"]["duong_di_that"]["bat"] is False


@pytest.mark.asyncio
async def test_khong_lo_bi_mat(api: AsyncClient, api_session: Session) -> None:
    api_session.add(Bin(code="BIN-X", name="Thùng X", device_key_hash="abc", is_active=True))
    api_session.commit()

    data = await _overview(api)
    van_ban = json.dumps(data, ensure_ascii=False)

    assert "jwt_secret" not in van_ban
    assert "greenbin-dev-secret" not in van_ban
    assert "BIN_DEVICE_KEY" not in van_ban
    assert re.search(r"(postgres(?:ql)?://|sqlite:///)", van_ban) is None, "Không được lộ chuỗi kết nối CSDL"
