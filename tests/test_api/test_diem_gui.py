"""Test API điểm gửi rác cho cư dân — bản thu gọn, không lộ dữ liệu vận hành."""

from __future__ import annotations

import itertools
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

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


# --- /bins/diem-gui --------------------------------------------------------


@pytest.mark.asyncio
async def test_cu_dan_goi_duoc_diem_gui(api: AsyncClient, api_session: Session) -> None:
    """Trước gói này cư dân gọi GET /bins bị 403 — nay có endpoint riêng."""
    _tao_thung(api_session)
    api_session.commit()
    token = await _dang_nhap(api, "resident@demo.vn")

    response = await api.get("/api/v1/bins/diem-gui", headers=_auth(token))

    assert response.status_code == 200, response.text
    assert isinstance(response.json()["items"], list)


@pytest.mark.asyncio
async def test_diem_gui_khong_lau_du_lieu_van_hanh(api: AsyncClient, api_session: Session) -> None:
    """Bản thu gọn phải bỏ mức pin, lần báo cuối và mã toà — thứ vận hành."""
    _tao_thung(api_session, battery_percent=40.0, last_seen_at=datetime.now(UTC))
    api_session.commit()
    token = await _dang_nhap(api, "resident@demo.vn")

    response = await api.get("/api/v1/bins/diem-gui", headers=_auth(token))

    assert response.status_code == 200, response.text
    diem = response.json()["items"][0]
    assert "battery_percent" not in diem
    assert "last_seen_at" not in diem
    assert "building_id" not in diem


@pytest.mark.asyncio
async def test_thung_day_bao_sap_day(api: AsyncClient, api_session: Session) -> None:
    """Vượt ngưỡng cảnh báo (mặc định 80%) là `sap_day` — vẫn còn nhận rác."""
    _tao_thung(api_session, fill_percent=92.0)
    api_session.commit()
    token = await _dang_nhap(api, "resident@demo.vn")

    response = await api.get("/api/v1/bins/diem-gui", headers=_auth(token))

    diem = response.json()["items"][0]
    assert diem["tinh_trang"] == "sap_day"
    assert diem["tinh_trang_vi"] == "Sắp đầy"
    assert diem["fill_percent"] == 92.0


@pytest.mark.asyncio
async def test_offline_bao_chua_ro_va_khong_tra_con_so_cu(api: AsyncClient, api_session: Session) -> None:
    """Mất kết nối thì mức đầy lưu có thể đã cũ — phải `chua_ro` kèm `fill_percent=None`."""
    _tao_thung(
        api_session,
        fill_percent=85.0,
        last_seen_at=datetime.now(UTC) - timedelta(days=3),
    )
    api_session.commit()
    token = await _dang_nhap(api, "resident@demo.vn")

    response = await api.get("/api/v1/bins/diem-gui", headers=_auth(token))

    diem = response.json()["items"][0]
    assert diem["tinh_trang"] == "chua_ro"
    assert diem["tinh_trang_vi"] == "Chưa rõ còn chỗ không"
    assert diem["fill_percent"] is None


@pytest.mark.asyncio
async def test_diem_gui_khong_roi_vao_duong_chi_tiet(api: AsyncClient, api_session: Session) -> None:
    """`/bins/diem-gui` phải là một endpoint riêng, không bị nuốt bởi `/bins/{code}`."""
    api_session.commit()
    token = await _dang_nhap(api, "resident@demo.vn")

    response = await api.get("/api/v1/bins/diem-gui", headers=_auth(token))

    assert response.status_code == 200, response.text
    assert "items" in response.json()
