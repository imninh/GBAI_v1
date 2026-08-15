"""Upload ảnh cho wizard thu gom — nối trọn vòng cư dân → BQL.

Cư dân đính ảnh (tuỳ chọn) vào từng món; BQL duyệt yêu cầu bằng ảnh thật thay vì
ô sọc giả (P40 đã dựng ``AnhCoToken`` nhưng ``media_id`` luôn rỗng vì không có
đường upload). Ba ca: upload hợp lệ, thiếu token, và đính ``media_id`` vào món
của yêu cầu thu gom rồi đọc lại qua ``pickup_dict``.
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from datetime import date, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.deps import get_db
from src.config import reset_settings_cache
from src.db.models import Base
from src.main import app

MAT_KHAU = "demo1234"


@pytest.fixture(autouse=True)
def _xoam_cache_cau_hinh() -> Iterator[None]:
    """Cấu hình đọc qua ``lru_cache`` nên phải xoá cache quanh mỗi test."""
    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture
def api_session(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Iterator[Session]:
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
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path / "media"))
    reset_settings_cache()

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


def _anh_jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (120, 200, 80)).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_upload_anh_hop_le_tra_media_id(api: AsyncClient, api_session: Session) -> None:
    """Ảnh hợp lệ → 200 + ``media_id`` là số nguyên (để đính vào món)."""
    token = await _dang_nhap(api, "resident@demo.vn")

    response = await api.post(
        "/api/v1/media",
        files={"image": ("mon.jpg", _anh_jpeg(), "image/jpeg")},
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body["media_id"], int)
    assert body["media_id"] > 0


@pytest.mark.asyncio
async def test_upload_khong_token_thi_401(api: AsyncClient, api_session: Session) -> None:
    """Không có token → 401: ảnh không bao giờ vào hệ thống mà không xác thực."""
    response = await api.post("/api/v1/media", files={"image": ("mon.jpg", _anh_jpeg(), "image/jpeg")})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_dinh_anh_vao_mon_roi_doc_lai_qua_pickup_dict(
    api: AsyncClient, api_session: Session
) -> None:
    """Upload rồi đính ``media_id`` vào món → yêu cầu trả lại đúng ``media_id`` đó."""
    token = await _dang_nhap(api, "resident@demo.vn")

    upload = await api.post(
        "/api/v1/media",
        files={"image": ("mon.jpg", _anh_jpeg(), "image/jpeg")},
        headers=_auth(token),
    )
    media_id = upload.json()["media_id"]

    response = await api.post(
        "/api/v1/pickups",
        json={
            "items": [
                {"name": "Tủ quần áo", "category_code": "bulky", "qty": 1, "media_id": media_id},
            ],
            "est_weight_kg": 10,
            "preferred_date": (date.today() + timedelta(days=3)).isoformat(),
            "preferred_window": "08:00-10:00",
            "confirmed_no_hazardous": True,
        },
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    mon = response.json()["items"][0]
    assert mon["media_id"] == media_id, "media_id phải chảy qua pickup_dict nguyên vẹn"
