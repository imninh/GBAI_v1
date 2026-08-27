"""Test đăng ký cư dân mới bằng số điện thoại — G1b, endpoint công khai."""

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
from src.db.models import Base, Building, Unit, User
from src.main import app
from src.services.gioi_han_tan_suat import dat_lai

MAT_KHAU = "demo1234"


@pytest.fixture(autouse=True)
def _xoam_cache_cau_hinh() -> Iterator[None]:
    # Bộ đếm tần suất của `/auth/register` sống ở cấp module nên nó KHÔNG tự
    # rỗng giữa hai test. File này gọi register 9 lần; không xoá thì test thứ
    # mấy đó bỗng nhận 429 và đỏ vì lý do chẳng liên quan gì tới nó.
    reset_settings_cache()
    dat_lai()
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


# --- Đăng ký ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_dang_ky_thanh_cong_va_vao_duoc_ngay(api: AsyncClient, api_session: Session) -> None:
    response = await api.post(
        "/api/v1/auth/register",
        json={"phone": "0912345678", "password": "matkhau123", "full_name": "Nguyễn Văn Mới"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["token"]
    assert body["user"]["role"] == "resident"
    assert body["user"]["phone"] == "0912345678"
    assert body["user"]["full_name"] == "Nguyễn Văn Mới"

    me = await api.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['token']}"})
    assert me.status_code == 200, me.text


@pytest.mark.asyncio
async def test_sdt_duoc_chuan_hoa_truoc_khi_luu(api: AsyncClient, api_session: Session) -> None:
    response = await api.post(
        "/api/v1/auth/register",
        json={"phone": "+84912345679", "password": "matkhau123", "full_name": "Nguyễn An"},
    )

    assert response.status_code == 201, response.text
    assert response.json()["user"]["phone"] == "0912345679"


@pytest.mark.asyncio
async def test_email_noi_bo_dung_dang(api: AsyncClient, api_session: Session) -> None:
    response = await api.post(
        "/api/v1/auth/register",
        json={"phone": "0912345680", "password": "matkhau123", "full_name": "Trần Bình"},
    )

    assert response.status_code == 201, response.text
    assert response.json()["user"]["email"] == "0912345680@sdt.local"


@pytest.mark.asyncio
async def test_dang_ky_kem_can_ho_thi_co_toa_do_noi_o(api: AsyncClient, api_session: Session) -> None:
    can_ho = api_session.scalar(select(Unit).where(Unit.code == "S1-0302"))
    assert can_ho is not None

    response = await api.post(
        "/api/v1/auth/register",
        json={"phone": "0912345681", "password": "matkhau123", "full_name": "Đỗ Cúc", "unit_id": can_ho.id},
    )

    assert response.status_code == 201, response.text
    user = response.json()["user"]
    assert user["unit"] == "S1-0302"
    assert user["building_lat"] is not None
    assert user["building_lng"] is not None


@pytest.mark.asyncio
async def test_so_da_co_tai_khoan_thi_409(api: AsyncClient, api_session: Session) -> None:
    response = await api.post(
        "/api/v1/auth/register",
        json={"phone": "0901000001", "password": "matkhau123", "full_name": "Phạm Dung"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REG-409"


@pytest.mark.asyncio
async def test_so_trung_o_dang_khac_van_bi_chan(api: AsyncClient, api_session: Session) -> None:
    """Cùng một số thật nhưng viết dạng `+84…` phải bị chặn — không được tạo tài khoản thứ hai."""
    so_truoc = _so_dong_user(api_session)

    response = await api.post(
        "/api/v1/auth/register",
        json={"phone": "+84901000001", "password": "matkhau123", "full_name": "Vũ Em"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REG-409"
    api_session.expire_all()
    assert _so_dong_user(api_session) == so_truoc


@pytest.mark.asyncio
async def test_so_khong_hop_le_thi_400(api: AsyncClient, api_session: Session) -> None:
    response = await api.post(
        "/api/v1/auth/register",
        json={"phone": "091234567", "password": "matkhau123", "full_name": "Lý Phúc"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "REG-400"


@pytest.mark.asyncio
async def test_can_ho_khong_ton_tai_thi_404_va_khong_tao_tai_khoan_rac(
    api: AsyncClient, api_session: Session
) -> None:
    so_truoc = _so_dong_user(api_session)

    response = await api.post(
        "/api/v1/auth/register",
        json={"phone": "0912345682", "password": "matkhau123", "full_name": "Hà Giang", "unit_id": 99999},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "REG-404"
    api_session.expire_all()
    assert _so_dong_user(api_session) == so_truoc


@pytest.mark.asyncio
async def test_client_khong_tu_phong_vai_tro_duoc(api: AsyncClient, api_session: Session) -> None:
    """Gửi kèm `role` và `green_points` thì bị bỏ qua — server luôn tự quyết."""
    response = await api.post(
        "/api/v1/auth/register",
        json={
            "phone": "0912345683",
            "password": "matkhau123",
            "full_name": "Ngô Hân",
            "role": "manager",
            "green_points": 9999,
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["user"]["role"] == "resident"
    assert body["user"]["green_points"] == 0
    assert body["permissions"]["review_route"]["allowed"] is False


# --- Liên kết nơi ở: building_id (gói worker 27/08) ---------------------------


def _toa_khong_co_phong(api_session: Session) -> Building:
    """Chọn một toà KHÔNG có căn hộ nào — 41/44 toà trong seed rơi vào nhóm này."""
    cac_toa_co_phong = {u.building_id for u in api_session.scalars(select(Unit)).all()}
    toa = api_session.scalar(select(Building).where(Building.id.notin_(cac_toa_co_phong)))
    assert toa is not None, "seed phải có ít nhất một toà không có phòng"
    return toa


@pytest.mark.asyncio
async def test_dang_ky_chi_toa_thanh_cong(api: AsyncClient, api_session: Session) -> None:
    """Chỉ gửi building_id (không căn) → tạo được, có toạ độ toà, unit rỗng."""
    toa = Building(code="KO-PHONG-1", name="Toà không phòng", address="9 Đường X", lat=10.0, lng=20.0)
    api_session.add(toa)
    api_session.flush()

    response = await api.post(
        "/api/v1/auth/register",
        json={"phone": "0912345980", "password": "matkhau123", "full_name": "Chỉ Toà", "building_id": toa.id},
    )

    assert response.status_code == 201, response.text
    user = response.json()["user"]
    assert user["building_id"] == toa.id
    assert user["unit"] == ""
    assert user["building_lat"] == toa.lat
    assert user["building_lng"] == toa.lng


@pytest.mark.asyncio
async def test_dang_ky_chi_can_ho_tu_dien_toa(api: AsyncClient, api_session: Session) -> None:
    """Chỉ gửi unit_id → server tự suy building từ căn (tương thích client cũ)."""
    can_ho = api_session.scalar(select(Unit).where(Unit.code == "S1-0302"))
    assert can_ho is not None

    response = await api.post(
        "/api/v1/auth/register",
        json={"phone": "0912345981", "password": "matkhau123", "full_name": "Chỉ Căn", "unit_id": can_ho.id},
    )

    assert response.status_code == 201, response.text
    user = response.json()["user"]
    assert user["unit"] == "S1-0302"
    assert user["building_id"] == can_ho.building_id


@pytest.mark.asyncio
async def test_dang_ky_toa_khac_can_ho_thi_400(api: AsyncClient, api_session: Session) -> None:
    """Gửi building_id và unit_id không khớp → 400 rõ nghĩa, không tạo tài khoản."""
    so_truoc = _so_dong_user(api_session)
    can_ho = api_session.scalar(select(Unit).where(Unit.code == "S1-0302"))
    toa_khac = api_session.scalar(select(Building).where(Building.id != can_ho.building_id))

    response = await api.post(
        "/api/v1/auth/register",
        json={
            "phone": "0912345982",
            "password": "matkhau123",
            "full_name": "Sai Khớp",
            "unit_id": can_ho.id,
            "building_id": toa_khac.id,
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "REG-400"
    api_session.expire_all()
    assert _so_dong_user(api_session) == so_truoc


@pytest.mark.asyncio
async def test_dang_ky_toa_khong_ton_tai_thi_404(api: AsyncClient, api_session: Session) -> None:
    so_truoc = _so_dong_user(api_session)

    response = await api.post(
        "/api/v1/auth/register",
        json={"phone": "0912345983", "password": "matkhau123", "full_name": "Toà Ảo", "building_id": 99999},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "REG-404"
    api_session.expire_all()
    assert _so_dong_user(api_session) == so_truoc
