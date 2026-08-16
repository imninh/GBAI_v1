"""Test API thùng — `category_codes` phải ra ngoài để cư dân lọc theo vật liệu."""

from __future__ import annotations

import itertools
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.deps import get_db
from src.config import reset_settings_cache
from src.db.models import Base, Bin
from src.main import app

MAT_KHAU = "demo1234"

_so_thung = itertools.count(1)


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


async def _dang_nhap(api: AsyncClient, email: str) -> str:
    response = await api.post("/api/v1/auth/login", json={"email": email, "password": MAT_KHAU})
    assert response.status_code == 200, response.text
    return response.json()["token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _tao_thung(session: Session, **fields: object) -> Bin:
    """Tạo một thùng cho test; mã tự sinh nếu không truyền."""
    defaults: dict[str, object] = {
        "code": f"BIN-{next(_so_thung):03d}",
        "name": "Thùng Bờ Hồ",
        "address": "Phố Đinh Tiên Hoàng, Hoàn Kiếm, Hà Nội",
        "lat": 21.0285,
        "lng": 105.8542,
        "fill_percent": 10.0,
        "battery_percent": 100.0,
        "last_seen_at": datetime.now(UTC),
        "is_active": True,
        "is_seed": False,
    }
    defaults.update(fields)
    thung = Bin(**defaults)
    session.add(thung)
    session.flush()
    return thung


# --- category_codes --------------------------------------------------------


@pytest.mark.asyncio
async def test_lay_danh_sach_tra_ve_category_codes(api: AsyncClient, api_session: Session) -> None:
    """GET /bins phải cho cư dân biết thùng nào nhận nhóm rác nào."""
    _tao_thung(
        api_session,
        code="BIN-NHUA-GIAY",
        category_codes=["recyclable_plastic", "recyclable_paper"],
    )
    api_session.commit()
    token = await _dang_nhap(api, "manager@demo.vn")

    response = await api.get("/api/v1/bins", headers=_auth(token))

    assert response.status_code == 200, response.text
    theo_ma = {i["code"]: i for i in response.json()["items"]}
    assert theo_ma["BIN-NHUA-GIAY"]["category_codes"] == ["recyclable_plastic", "recyclable_paper"]


@pytest.mark.asyncio
async def test_category_codes_null_thanh_mang_rong(api: AsyncClient, api_session: Session) -> None:
    """Cột cho phép NULL với bản ghi cũ — phải ra `[]`, không ra `null` và không nổ."""
    _tao_thung(api_session, code="BIN-KHONG-NHOM", category_codes=None)
    api_session.commit()
    token = await _dang_nhap(api, "manager@demo.vn")

    response = await api.get("/api/v1/bins", headers=_auth(token))

    assert response.status_code == 200, response.text
    theo_ma = {i["code"]: i for i in response.json()["items"]}
    assert theo_ma["BIN-KHONG-NHOM"]["category_codes"] == []


@pytest.mark.asyncio
async def test_chi_tiet_thung_cung_mang_category_codes(api: AsyncClient, api_session: Session) -> None:
    """Màn chi tiết thùng cũng cần lọc theo vật liệu nên trường phải có mặt."""
    _tao_thung(api_session, code="BIN-CHI-TIET-NHOM", category_codes=["recyclable_glass"])
    api_session.commit()
    token = await _dang_nhap(api, "manager@demo.vn")

    response = await api.get("/api/v1/bins/BIN-CHI-TIET-NHOM", headers=_auth(token))

    assert response.status_code == 200, response.text
    assert response.json()["category_codes"] == ["recyclable_glass"]
