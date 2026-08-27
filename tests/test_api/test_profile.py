"""Test hồ sơ cư dân — R-08: xem và tự sửa thông tin của mình."""

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
from src.db.models import AuditLog, Base, Building, Unit, User
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
    """Đăng nhập, trả về token Bearer."""
    response = await api.post("/api/v1/auth/login", json={"email": email, "password": MAT_KHAU})
    assert response.status_code == 200, response.text
    return response.json()["token"]


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- Sửa hồ sơ -------------------------------------------------------------


@pytest.mark.asyncio
async def test_sua_duoc_ten_hien_thi(api: AsyncClient, api_session: Session) -> None:
    """Sửa tên xong thì `GET /me` phải thấy tên mới, và khoảng trắng bị cắt."""
    token = await _dang_nhap(api, "resident@demo.vn")

    response = await api.patch(
        "/api/v1/auth/me", json={"full_name": "  Trần Thị Mai  "}, headers=_bearer(token)
    )

    assert response.status_code == 200, response.text
    assert response.json()["user"]["full_name"] == "Trần Thị Mai"

    lai = await api.get("/api/v1/auth/me", headers=_bearer(token))
    assert lai.json()["user"]["full_name"] == "Trần Thị Mai"


@pytest.mark.asyncio
async def test_ten_toan_khoang_trang_bi_tu_choi(api: AsyncClient, api_session: Session) -> None:
    token = await _dang_nhap(api, "resident@demo.vn")

    response = await api.patch("/api/v1/auth/me", json={"full_name": "   "}, headers=_bearer(token))

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "REQ-400"


@pytest.mark.asyncio
async def test_doi_can_ho_thi_toa_do_noi_o_doi_theo(api: AsyncClient, api_session: Session) -> None:
    """Đổi căn hộ là đổi mốc sắp xếp điểm gửi ở app cư dân — phải khớp toà mới."""
    token = await _dang_nhap(api, "resident@demo.vn")
    can_ho = api_session.scalar(select(Unit).where(Unit.code == "S3-0710"))
    assert can_ho is not None
    toa = api_session.get(Building, can_ho.building_id)
    assert toa is not None

    response = await api.patch("/api/v1/auth/me", json={"unit_id": can_ho.id}, headers=_bearer(token))

    assert response.status_code == 200, response.text
    user = response.json()["user"]
    assert user["unit"] == "S3-0710"
    assert user["building_lat"] == toa.lat
    assert user["building_lng"] == toa.lng


@pytest.mark.asyncio
async def test_can_ho_khong_ton_tai_thi_404_va_khong_doi_gi(
    api: AsyncClient, api_session: Session
) -> None:
    token = await _dang_nhap(api, "resident@demo.vn")
    truoc = api_session.scalar(select(User).where(User.email == "resident@demo.vn")).unit_id

    response = await api.patch("/api/v1/auth/me", json={"unit_id": 99999}, headers=_bearer(token))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NF-404"
    api_session.expire_all()
    sau = api_session.scalar(select(User).where(User.email == "resident@demo.vn")).unit_id
    assert sau == truoc


@pytest.mark.asyncio
async def test_khong_sua_duoc_vai_tro_va_email(api: AsyncClient, api_session: Session) -> None:
    """Gửi kèm `role` và `email` thì bị bỏ qua, không phải được nhận."""
    token = await _dang_nhap(api, "resident@demo.vn")

    response = await api.patch(
        "/api/v1/auth/me",
        json={"full_name": "Vẫn là cư dân", "role": "manager", "email": "ke-gian@test.vn"},
        headers=_bearer(token),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user"]["role"] == "resident"
    assert body["user"]["email"] == "resident@demo.vn"
    assert body["permissions"]["review_route"]["allowed"] is False


@pytest.mark.asyncio
async def test_xoa_can_ho_thi_khong_con_toa_do(api: AsyncClient, api_session: Session) -> None:
    """Bỏ căn hộ thì toạ độ về `None`, app cư dân phải chịu được trạng thái này."""
    token = await _dang_nhap(api, "resident@demo.vn")

    response = await api.patch("/api/v1/auth/me", json={"xoa_can_ho": True}, headers=_bearer(token))

    assert response.status_code == 200, response.text
    user = response.json()["user"]
    assert user["unit"] == ""
    assert user["building_lat"] is None
    assert user["building_lng"] is None


@pytest.mark.asyncio
async def test_ghi_audit_log_kem_gia_tri_truoc_khi_sua(
    api: AsyncClient, api_session: Session
) -> None:
    """Nhật ký phải giữ được giá trị TRƯỚC khi sửa — không có nó thì log vô dụng."""
    token = await _dang_nhap(api, "resident@demo.vn")

    await api.patch("/api/v1/auth/me", json={"full_name": "Tên mới toanh"}, headers=_bearer(token))

    logs = api_session.scalars(select(AuditLog).where(AuditLog.action == "update_profile")).all()
    assert len(logs) == 1
    assert logs[0].entity == "user"
    assert logs[0].detail["truoc"]["full_name"] == "Nguyễn Thị Lan"
    assert logs[0].detail["sau"]["full_name"] == "Tên mới toanh"


# --- Danh sách căn hộ ------------------------------------------------------


@pytest.mark.asyncio
async def test_danh_sach_can_ho_cua_mot_toa(api: AsyncClient, api_session: Session) -> None:
    toa = api_session.scalar(select(Building).where(Building.code == "S1"))
    assert toa is not None

    response = await api.get(f"/api/v1/buildings/{toa.id}/units")

    assert response.status_code == 200, response.text
    ma = [u["code"] for u in response.json()["items"]]
    assert ma == ["S1-0302", "S1-0805", "S1-1203", "S1-1508"]


@pytest.mark.asyncio
async def test_toa_khong_ton_tai_thi_404(api: AsyncClient, api_session: Session) -> None:
    response = await api.get("/api/v1/buildings/99999/units")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NF-404"


# --- Sửa liên kết toà nhà (gói worker 27/08) ---------------------------------


@pytest.mark.asyncio
async def test_chuyen_sang_toa_khong_co_unit_thi_xoa_can_cu(
    api: AsyncClient, api_session: Session
) -> None:
    """Chuyển sang toà không có căn hộ → không để lại căn của toà cũ."""
    token = await _dang_nhap(api, "resident@demo.vn")
    can_ho = api_session.scalar(select(Unit).where(Unit.code == "S3-0710"))
    res = await api.patch("/api/v1/auth/me", json={"unit_id": can_ho.id}, headers=_bearer(token))
    assert res.status_code == 200, res.text

    cac_toa_co_phong = {u.building_id for u in api_session.scalars(select(Unit)).all()}
    toa = Building(code="KO-PHONG-PROFILE", name="Toà không phòng", address="9 Đường X", lat=10.0, lng=20.0)
    api_session.add(toa)
    api_session.flush()

    res2 = await api.patch("/api/v1/auth/me", json={"building_id": toa.id}, headers=_bearer(token))
    assert res2.status_code == 200, res2.text
    user = res2.json()["user"]
    assert user["building_id"] == toa.id
    assert user["unit"] == ""
    assert user["building_lat"] == toa.lat


@pytest.mark.asyncio
async def test_xoa_toa_thi_bo_ca_can(api: AsyncClient, api_session: Session) -> None:
    token = await _dang_nhap(api, "resident@demo.vn")
    can_ho = api_session.scalar(select(Unit).where(Unit.code == "S3-0710"))
    await api.patch("/api/v1/auth/me", json={"unit_id": can_ho.id}, headers=_bearer(token))

    res = await api.patch("/api/v1/auth/me", json={"xoa_toa": True}, headers=_bearer(token))
    assert res.status_code == 200, res.text
    user = res.json()["user"]
    assert user["building_id"] is None
    assert user["unit"] == ""


@pytest.mark.asyncio
async def test_building_khac_can_ho_thi_400(api: AsyncClient, api_session: Session) -> None:
    token = await _dang_nhap(api, "resident@demo.vn")
    can_ho = api_session.scalar(select(Unit).where(Unit.code == "S3-0710"))
    toa_khac = api_session.scalar(select(Building).where(Building.id != can_ho.building_id))

    res = await api.patch(
        "/api/v1/auth/me",
        json={"unit_id": can_ho.id, "building_id": toa_khac.id},
        headers=_bearer(token),
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "REQ-400"
