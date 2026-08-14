"""Gói P47 — màn BQL "Xếp tuyến": nhìn thấy nhóm ``cho_nhan`` và gọi propose.

Hai test đầu là guard quét văn bản frontend (đúng khuôn các gói trước: không chạy
code trình duyệt, chỉ đọc file). Hai test sau chạy API thật bằng fixture trong bộ
nhớ như các test khác trong ``tests/test_api/``.

Điểm khoá của gói: mục nav gate bằng quyền ``review_route`` (chỉ BQL thấy), và
màn Xếp tuyến CHỈ tạo tuyến ``proposed`` — cư dân gọi ``/routes/propose`` phải
bị 403.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

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
from src.services.pickup_lifecycle import CHO_NHAN, trang_thai_tuong_duong

MAT_KHAU = "demo1234"
GOC_DU_AN = Path(__file__).resolve().parents[2]

CONSOLE = GOC_DU_AN / "frontend" / "src" / "components" / "manager" / "console.tsx"
XEP_TUYEN = GOC_DU_AN / "frontend" / "src" / "components" / "manager" / "xep-tuyen.tsx"


# --- Guard quét văn bản ----------------------------------------------------


def test_console_co_muc_xep_tuyen() -> None:
    """Console phải có mục nav "Xếp tuyến" và nhánh render ra `XepTuyen`.

    Nếu BQL không bấm được vào màn, toàn bộ endpoint có sẵn vẫn vô dụng.
    """
    noi_dung = CONSOLE.read_text(encoding="utf-8")
    assert "xep_tuyen" in noi_dung, "console.tsx phải có key nav xep_tuyen"
    assert "<XepTuyen" in noi_dung, "console.tsx phải render <XepTuyen"
    assert '"Xếp tuyến"' in noi_dung, 'Nhãn mục nav phải là "Xếp tuyến"'


def test_xep_tuyen_goi_dung_endpoint() -> None:
    """Màn Xếp tuyến phải đọc đúng hai endpoint có sẵn: danh sách ``cho_nhan``
    và ``POST /routes/propose``. Không được tự duyệt tuyến ở màn này."""
    noi_dung = XEP_TUYEN.read_text(encoding="utf-8")
    assert "proposeRoute" in noi_dung or "/routes/propose" in noi_dung, "Màn phải gọi proposeRoute"
    assert "cho_nhan" in noi_dung or "pickupsChoNhan" in noi_dung, "Màn phải tải danh sách cho_nhan"
    assert "reviewRoute" not in noi_dung, "Màn Xếp tuyến KHÔNG được tự duyệt tuyến"
    assert "/routes/" not in noi_dung.replace("/routes/propose", ""), "Chỉ được gọi đúng /routes/propose"


# --- API thật --------------------------------------------------------------


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


async def _dang_nhap(api: AsyncClient, email: str) -> str:
    response = await api.post("/api/v1/auth/login", json={"email": email, "password": MAT_KHAU})
    assert response.status_code == 200, response.text
    return response.json()["token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _tao_yeu_cau_cho_nhan(api: AsyncClient, token: str) -> dict:
    """Tạo yêu cầu dưới ngưỡng → tự động ở trạng thái ``cho_nhan``."""
    response = await api.post(
        "/api/v1/pickups",
        json={
            "items": [{"name": "Thùng carton", "category_code": "recyclable_paper", "qty": 2}],
            "est_weight_kg": 8,
            "preferred_date": (date.today() + timedelta(days=3)).isoformat(),
            "preferred_window": "08:00-10:00",
            "confirmed_no_hazardous": True,
        },
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cho_nhan"
    return response.json()


@pytest.mark.asyncio
async def test_propose_can_quyen_review_route(api: AsyncClient) -> None:
    """Cư dân gọi ``POST /routes/propose`` phải bị chặn (thiếu ``review_route``).

    BQL (có quyền) thì không bị 403 — tạo xong tuyến phải ở trạng thái
    ``proposed``, tuyệt đối không tự duyệt.
    """
    resident = await _dang_nhap(api, "resident@demo.vn")
    manager = await _dang_nhap(api, "manager@demo.vn")
    ngay = (date.today() + timedelta(days=3)).isoformat()

    response = await api.post(
        "/api/v1/routes/propose",
        json={"service_date": ngay, "window": "08:00-10:00"},
        headers=_auth(resident),
    )
    assert response.status_code in (401, 403), f"Cư dân phải bị chặn, gặp {response.status_code}: {response.text}"

    await _tao_yeu_cau_cho_nhan(api, resident)

    response = await api.post(
        "/api/v1/routes/propose",
        json={"service_date": ngay, "window": "08:00-10:00"},
        headers=_auth(manager),
    )
    assert response.status_code != 403, f"BQL phải có quyền xếp tuyến: {response.text}"
    if response.status_code == 200:
        assert response.json()["status"] == "proposed", "Tuyến tạo ra phải ở trạng thái đề xuất"


@pytest.mark.asyncio
async def test_list_cho_nhan_loc_dung(api: AsyncClient) -> None:
    """``GET /pickups?status=cho_nhan`` chỉ trả về yêu cầu thuộc nhóm ``cho_nhan``."""
    resident = await _dang_nhap(api, "resident@demo.vn")
    manager = await _dang_nhap(api, "manager@demo.vn")
    yeu_cau = await _tao_yeu_cau_cho_nhan(api, resident)

    response = await api.get("/api/v1/pickups?status=cho_nhan", headers=_auth(manager))
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert items, "Phải có ít nhất yêu cầu vừa tạo trong danh sách cho_nhan"
    assert any(item["id"] == yeu_cau["id"] for item in items), "Yêu cầu vừa tạo phải nằm trong danh sách"
    nhom = trang_thai_tuong_duong(CHO_NHAN)
    assert all(item["status"] in nhom for item in items), "Mọi mục phải thuộc nhóm cho_nhan"
