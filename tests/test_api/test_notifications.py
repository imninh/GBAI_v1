"""Test trung tâm thông báo — đọc thông báo + sự kiện gửi thứ 6.

Không test nào gọi API model thật — toàn bộ đi qua ASGITransport trên CSDL
trong bộ nhớ, đúng kiểu các file test API khác trong thư mục này.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from scripts.seed import seed_buildings, seed_categories, seed_knowledge, seed_schedules, seed_units, seed_users
from src.api.deps import get_db
from src.config import reset_settings_cache
from src.db.models import Base, Notification, User
from src.main import app
from src.services import pickup
from src.services.security import hash_password

MAT_KHAU = "demo1234"


@pytest.fixture(autouse=True)
def _xoam_cache_cau_hinh() -> Iterator[None]:
    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture
def api_session(monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
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


def _nguoi(api_session: Session, email: str) -> User:
    nguoi = api_session.scalar(select(User).where(User.email == email))
    assert nguoi is not None
    return nguoi


def _them_thong_bao(api_session: Session, user_id: int, title: str = "Tin mới") -> Notification:
    tb = Notification(user_id=user_id, title=title, body="nội dung", entity="phien_thung", entity_id="1")
    api_session.add(tb)
    api_session.flush()
    return tb


# --- POST /notifications/read -----------------------------------------------


@pytest.mark.asyncio
async def test_doc_thong_bao_chi_doc_cua_minh(api: AsyncClient, api_session: Session) -> None:
    """Đánh dấu đọc bằng id của NGƯỜI KHÁC → không ảnh hưởng, trả ok."""
    nguoi_a = _nguoi(api_session, "resident@demo.vn")
    nguoi_b = _nguoi(api_session, "resident3@demo.vn")
    tb_a = _them_thong_bao(api_session, nguoi_a.id)
    tb_b = _them_thong_bao(api_session, nguoi_b.id)

    token_a = await _dang_nhap(api, nguoi_a.email)
    response = await api.post(
        "/api/v1/notifications/read",
        json={"ids": [tb_b.id]},
        headers=_auth(token_a),
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"ok": True}

    api_session.expire_all()
    assert api_session.get(Notification, tb_a.id).read_at is None, "Không đụng thông báo của mình"
    assert api_session.get(Notification, tb_b.id).read_at is None, "Không đọc được thông báo của người khác"


@pytest.mark.asyncio
async def test_doc_thong_bao_theo_ids(api: AsyncClient, api_session: Session) -> None:
    nguoi = _nguoi(api_session, "resident@demo.vn")
    tb_1 = _them_thong_bao(api_session, nguoi.id)
    tb_2 = _them_thong_bao(api_session, nguoi.id)

    token = await _dang_nhap(api, nguoi.email)
    response = await api.post(
        "/api/v1/notifications/read",
        json={"ids": [tb_1.id]},
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text

    api_session.expire_all()
    assert api_session.get(Notification, tb_1.id).read_at is not None
    assert api_session.get(Notification, tb_2.id).read_at is None, "Chỉ đọc đúng id được gửi"

    thong_bao = (await api.get("/api/v1/notifications", headers=_auth(token))).json()
    assert thong_bao["unread"] == 1


@pytest.mark.asyncio
async def test_doc_thong_bao_null_thi_doc_het(api: AsyncClient, api_session: Session) -> None:
    nguoi = _nguoi(api_session, "resident@demo.vn")
    tb_1 = _them_thong_bao(api_session, nguoi.id)
    tb_2 = _them_thong_bao(api_session, nguoi.id)

    token = await _dang_nhap(api, nguoi.email)
    response = await api.post("/api/v1/notifications/read", json={"ids": None}, headers=_auth(token))
    assert response.status_code == 200, response.text

    api_session.expire_all()
    assert api_session.get(Notification, tb_1.id).read_at is not None
    assert api_session.get(Notification, tb_2.id).read_at is not None


@pytest.mark.asyncio
async def test_doc_thong_bao_body_trong_van_ok(api: AsyncClient, api_session: Session) -> None:
    nguoi = _nguoi(api_session, "resident@demo.vn")
    token = await _dang_nhap(api, nguoi.email)
    response = await api.post("/api/v1/notifications/read", json={"ids": []}, headers=_auth(token))
    assert response.status_code == 200, response.text
    assert response.json() == {"ok": True}


# --- Sự kiện thứ 6: cư dân tạo yêu cầu → manager cùng toà -------------------


def test_tao_yeu_cau_gui_cho_manager_cung_toa(db_session: Session) -> None:
    from src.db.models import Building, Unit

    toa = Building(code="N1", name="Toà N1", lat=21.0285, lng=105.8542)
    db_session.add(toa)
    db_session.flush()
    can_ho = Unit(building_id=toa.id, code="N1-101")
    db_session.add(can_ho)
    db_session.flush()

    cu_dan = User(
        email="cu-dan-n1@demo.vn",
        full_name="Cư dân N1",
        role="resident",
        password_hash=hash_password(MAT_KHAU),
        unit_id=can_ho.id,
    )
    quan_ly_cung_toa = User(
        email="ql-n1@demo.vn",
        full_name="Quản lý N1",
        role="manager",
        password_hash=hash_password(MAT_KHAU),
        building_id=toa.id,
    )
    quan_ly_toa_khac = User(
        email="ql-n2@demo.vn",
        full_name="Quản lý N2",
        role="manager",
        password_hash=hash_password(MAT_KHAU),
        building_id=toa.id + 999,
    )
    db_session.add_all([cu_dan, quan_ly_cung_toa, quan_ly_toa_khac])
    db_session.flush()

    pickup.create_pickup_request(
        db_session,
        resident=cu_dan,
        items=[{"name": "Tủ gỗ cũ", "category_code": "bulky", "qty": 1}],
        est_weight_kg=10
    )
    db_session.flush()

    cac_tb = db_session.scalars(
        select(Notification).where(Notification.entity == "yeu_cau_thu_gom")
    ).all()
    assert len(cac_tb) == 1, "Chỉ manager cùng toà nhận, không nhắn sang toà khác"
    tb = cac_tb[0]
    assert tb.user_id == quan_ly_cung_toa.id
    assert tb.title == "Có yêu cầu thu gom mới"
    assert "Cư dân N1" in tb.body


def test_tao_yeu_cau_khong_co_manager_cung_toa_thi_bo_qua(db_session: Session) -> None:
    from src.db.models import Building, Unit

    toa = Building(code="N2", name="Toà N2", lat=21.0285, lng=105.8542)
    db_session.add(toa)
    db_session.flush()
    can_ho = Unit(building_id=toa.id, code="N2-101")
    db_session.add(can_ho)
    db_session.flush()

    cu_dan = User(
        email="cu-dan-n2@demo.vn",
        full_name="Cư dân N2",
        role="resident",
        password_hash=hash_password(MAT_KHAU),
        unit_id=can_ho.id,
    )
    db_session.add(cu_dan)
    db_session.flush()

    pickup.create_pickup_request(
        db_session,
        resident=cu_dan,
        items=[{"name": "Tủ gỗ cũ", "category_code": "bulky", "qty": 1}],
        est_weight_kg=10
    )
    db_session.flush()

    so_tb = db_session.scalar(
        select(Notification).where(Notification.entity == "yeu_cau_thu_gom")
    )
    assert so_tb is None, "Không có manager cùng toà thì không gửi, không lỗi"
