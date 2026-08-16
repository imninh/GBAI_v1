"""Giới hạn tần suất cho ``POST /auth/register`` — gói P11.

Bốn test đầu gọi thẳng hàm thuần ``cho_phep`` (nhanh, không cần HTTP); hai test
cuối đi qua API thật, dựng client và CSDL đúng cách ``tests/test_api/test_dang_ky.py``
đang làm.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.deps import get_db
from src.config import reset_settings_cache
from src.db.models import Base, User
from src.main import app
from src.services.gioi_han_tan_suat import cho_phep, dat_lai


@pytest.fixture(autouse=True)
def _dau_vet_sach() -> Iterator[None]:
    # Bộ đếm tần suất sống ở cấp module nên nó không tự rỗng giữa hai test.
    # Xoá trước và sau mỗi test để kết quả không phụ thuộc thứ tự chạy.
    dat_lai()
    reset_settings_cache()
    yield
    dat_lai()
    reset_settings_cache()


@pytest.fixture
def api_session(monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
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


def _so_dong_user(api_session: Session) -> int:
    return api_session.scalar(select(func.count(User.id))) or 0


# --- Hàm thuần `cho_phep` ---------------------------------------------------


def test_duoi_gioi_han_thi_cho_qua() -> None:
    assert cho_phep("ip-a", 3, 600, bay_gio=0) is True
    assert cho_phep("ip-a", 3, 600, bay_gio=0) is True
    assert cho_phep("ip-a", 3, 600, bay_gio=0) is True


def test_vuot_gioi_han_thi_chan() -> None:
    for _ in range(3):
        assert cho_phep("ip-a", 3, 600, bay_gio=0) is True
    assert cho_phep("ip-a", 3, 600, bay_gio=0) is False


def test_bi_chan_roi_van_bam_thu_lai_thi_van_mo_lai_dung_han() -> None:
    """Chốt chặn quan trọng nhất: lời hứa là "chặn 10 phút", không phải "chặn
    10 phút tính từ lần bấm cuối cùng". Mấy lần bấm bị từ chối KHÔNG được đẩy
    hạn mở khoá đi xa thêm."""
    assert cho_phep("ip-a", 3, 600, bay_gio=0) is True
    assert cho_phep("ip-a", 3, 600, bay_gio=0) is True
    assert cho_phep("ip-a", 3, 600, bay_gio=0) is True

    assert cho_phep("ip-a", 3, 600, bay_gio=0) is False

    assert cho_phep("ip-a", 3, 600, bay_gio=100) is False
    assert cho_phep("ip-a", 3, 600, bay_gio=200) is False
    assert cho_phep("ip-a", 3, 600, bay_gio=300) is False

    assert cho_phep("ip-a", 3, 600, bay_gio=601) is True


def test_gioi_han_bang_khong_la_tat_han() -> None:
    for _ in range(50):
        assert cho_phep("ip-a", 0, 600, bay_gio=0) is True


# --- Đi qua API thật --------------------------------------------------------


@pytest.mark.asyncio
async def test_dang_ky_qua_gioi_han_thi_tra_429(
    api: AsyncClient, api_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REGISTER_RATE_LIMIT", "2")
    reset_settings_cache()

    for so in ("0912999001", "0912999002"):
        r = await api.post(
            "/api/v1/auth/register",
            json={"phone": so, "password": "matkhau123", "full_name": "Bùi Vừa"},
        )
        assert r.status_code == 201, r.text

    r = await api.post(
        "/api/v1/auth/register",
        json={"phone": "0912999003", "password": "matkhau123", "full_name": "Bùi Chặn"},
    )
    assert r.status_code == 429, r.text
    body = r.json()
    assert body["error"]["code"] == "RATE-429"
    assert body["error"]["message_vi"] == (
        "Bạn đã thử đăng ký quá nhiều lần. Chờ ít phút rồi thử lại giúp mình nhé."
    )


@pytest.mark.asyncio
async def test_bi_chan_thi_khong_de_lai_tai_khoan_rac(
    api: AsyncClient, api_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REGISTER_RATE_LIMIT", "2")
    reset_settings_cache()

    for so in ("0912999101", "0912999102"):
        r = await api.post(
            "/api/v1/auth/register",
            json={"phone": so, "password": "matkhau123", "full_name": "Ngô Hậu"},
        )
        assert r.status_code == 201, r.text

    so_truoc = _so_dong_user(api_session)
    r = await api.post(
        "/api/v1/auth/register",
        json={"phone": "0912999103", "password": "matkhau123", "full_name": "Ngô Tới"},
    )
    assert r.status_code == 429, r.text
    api_session.expire_all()
    assert _so_dong_user(api_session) == so_truoc, "Lần gọi bị 429 không được để lại tài khoản rác"
