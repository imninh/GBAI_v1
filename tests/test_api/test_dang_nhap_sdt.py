"""Test đăng nhập bằng số điện thoại — G1a, đường email không được hỏng."""

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
from src.services.auth import chuan_hoa_sdt

MAT_KHAU = "demo1234"


@pytest.fixture(autouse=True)
def _xoam_cache_cau_hinh() -> Iterator[None]:
    reset_settings_cache()
    yield
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


# --- Chuẩn hoá SĐT ---------------------------------------------------------


def test_chuan_hoa_sdt_nhan_moi_dang_nguoi_ta_hay_go() -> None:
    """Bốn cách gõ khác nhau phải ra cùng một số; đầu vào lạ thì ra chuỗi rỗng."""
    for nhap in ["0912345678", "0912 345 678", "0912.345.678", "+84912345678", "84912345678"]:
        assert chuan_hoa_sdt(nhap) == "0912345678", nhap
    for nhap in ["resident@demo.vn", "091234567", "09123456789", "1912345678", ""]:
        assert chuan_hoa_sdt(nhap) == "", nhap


# --- Đăng nhập -------------------------------------------------------------


@pytest.mark.asyncio
async def test_dang_nhap_bang_so_dien_thoai(api: AsyncClient, api_session: Session) -> None:
    """SĐT chuẩn đăng nhập được, và token dùng được cho `/auth/me`."""
    response = await api.post(
        "/api/v1/auth/login", json={"phone": "0901000001", "password": MAT_KHAU}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user"]["email"] == "resident@demo.vn"
    assert body["user"]["phone"] == "0901000001"

    me = await api.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['token']}"})
    assert me.status_code == 200, me.text


@pytest.mark.asyncio
async def test_sdt_go_co_khoang_trang_van_dang_nhap_duoc(api: AsyncClient, api_session: Session) -> None:
    response = await api.post(
        "/api/v1/auth/login", json={"phone": "0901 000 001", "password": MAT_KHAU}
    )

    assert response.status_code == 200, response.text
    assert response.json()["user"]["email"] == "resident@demo.vn"


@pytest.mark.asyncio
async def test_ba_nut_demo_van_dang_nhap_bang_email_duoc(api: AsyncClient, api_session: Session) -> None:
    """Ba nút "vào thẳng" của màn đăng nhập KHÔNG được hỏng — đó là cách người chấm vào hệ thống."""
    for email, role in [
        ("resident@demo.vn", "resident"),
        ("cleaner@demo.vn", "cleaner"),
        ("manager@demo.vn", "manager"),
    ]:
        response = await api.post(
            "/api/v1/auth/login", json={"email": email, "password": MAT_KHAU}
        )
        assert response.status_code == 200, f"{email}: {response.text}"
        assert response.json()["user"]["role"] == role, email


@pytest.mark.asyncio
async def test_sai_mat_khau_bao_giong_het_nhau_du_go_sdt_hay_email(
    api: AsyncClient, api_session: Session
) -> None:
    """Sai mật khẩu bằng SĐT và bằng email phải ra cùng mã lỗi, cùng câu chữ."""
    qua_sdt = await api.post("/api/v1/auth/login", json={"phone": "0901000001", "password": "sai-sai"})
    qua_email = await api.post("/api/v1/auth/login", json={"email": "resident@demo.vn", "password": "sai-sai"})

    assert qua_sdt.status_code == 401
    assert qua_email.status_code == 401
    loi_sdt = qua_sdt.json()["error"]
    loi_email = qua_email.json()["error"]
    assert loi_sdt["code"] == loi_email["code"] == "AUTH-401"
    assert loi_sdt["message_vi"] == loi_email["message_vi"]


@pytest.mark.asyncio
async def test_so_chua_dang_ky_cung_bao_y_het_nhu_sai_mat_khau(
    api: AsyncClient, api_session: Session
) -> None:
    """SĐT chưa đăng ký không được lộ rằng số đó không tồn tại."""
    response = await api.post("/api/v1/auth/login", json={"phone": "0999999999", "password": MAT_KHAU})

    assert response.status_code == 401
    loi = response.json()["error"]
    assert loi["code"] == "AUTH-401"
    assert loi["message_vi"] == "Số điện thoại/email hoặc mật khẩu không đúng."


@pytest.mark.asyncio
async def test_khong_gui_ca_sdt_lan_email_thi_400(api: AsyncClient, api_session: Session) -> None:
    response = await api.post("/api/v1/auth/login", json={"password": MAT_KHAU})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "REQ-400"


@pytest.mark.asyncio
async def test_phan_hoi_dang_nhap_co_truong_phone(api: AsyncClient, api_session: Session) -> None:
    """UserOut phải khai `phone`, nếu không FastAPI cắt mất trường này khỏi phản hồi."""
    response = await api.post("/api/v1/auth/login", json={"email": "resident@demo.vn", "password": MAT_KHAU})

    assert response.status_code == 200, response.text
    assert "phone" in response.json()["user"]
