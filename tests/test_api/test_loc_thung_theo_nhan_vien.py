"""Nửa ĐỌC của gói A2b — lọc danh sách thùng theo người đang đăng nhập.

Nhân viên vệ sinh chỉ thấy thùng được giao cho mình; ban quản lý thấy toàn bộ,
kể cả thùng chưa giao ai. Mở chi tiết thùng không thuộc về mình phải trả 404 với
cùng câu lỗi của thùng không tồn tại — không được phép 403 vì 403 xác nhận "mã
thùng có thật" (dò mã bằng cách thử lần lượt).
"""

from __future__ import annotations

import itertools
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.deps import get_db
from src.config import reset_settings_cache
from src.db.models import Base, Bin, User
from src.main import app
from src.services import bins

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


@pytest_asyncio.fixture
async def boi_canh(api: AsyncClient, api_session: Session) -> dict[str, object]:
    """Bốn thùng: BIN-A1/BIN-A2 giao cho nhân viên A, BIN-B1 cho B, BIN-CHUA chưa gán.

    Kèm token của A, ban quản lý và cư dân — nhân viên B không cần token vì
    không test nào đăng nhập bằng vai đó.
    """
    nhan_vien_a = api_session.scalar(select(User).where(User.email == "cleaner@demo.vn"))
    nhan_vien_b = User(
        email="cleaner-b@demo.vn",
        full_name="Nhân viên vệ sinh B",
        role="cleaner",
        password_hash="x",
    )
    api_session.add(nhan_vien_b)
    api_session.flush()

    thung_a1 = _tao_thung(api_session, code="BIN-A1")
    thung_a2 = _tao_thung(api_session, code="BIN-A2")
    thung_b1 = _tao_thung(api_session, code="BIN-B1")
    _tao_thung(api_session, code="BIN-CHUA")
    thung_a1.assigned_cleaner_id = nhan_vien_a.id
    thung_a2.assigned_cleaner_id = nhan_vien_a.id
    thung_b1.assigned_cleaner_id = nhan_vien_b.id
    api_session.commit()

    return {
        "token_a": await _dang_nhap(api, "cleaner@demo.vn"),
        "token_manager": await _dang_nhap(api, "manager@demo.vn"),
        "token_resident": await _dang_nhap(api, "resident@demo.vn"),
        "id_a": nhan_vien_a.id,
    }


@pytest.mark.asyncio
async def test_nhan_vien_chi_thay_thung_cua_minh(api: AsyncClient, boi_canh: dict[str, object]) -> None:
    response = await api.get("/api/v1/bins", headers=_auth(boi_canh["token_a"]))

    assert response.status_code == 200, response.text
    codes = [i["code"] for i in response.json()["items"]]
    assert sorted(codes) == ["BIN-A1", "BIN-A2"]


@pytest.mark.asyncio
async def test_quan_ly_thay_tat_ca_ke_ca_thung_chua_gan(api: AsyncClient, boi_canh: dict[str, object]) -> None:
    response = await api.get("/api/v1/bins", headers=_auth(boi_canh["token_manager"]))

    assert response.status_code == 200, response.text
    codes = [i["code"] for i in response.json()["items"]]
    assert sorted(codes) == ["BIN-A1", "BIN-A2", "BIN-B1", "BIN-CHUA"]


@pytest.mark.asyncio
async def test_stats_cua_nhan_vien_dem_theo_phan_duoc_giao(api: AsyncClient, boi_canh: dict[str, object]) -> None:
    response = await api.get("/api/v1/bins/stats", headers=_auth(boi_canh["token_a"]))

    assert response.status_code == 200, response.text
    assert response.json()["tong"] == 2


@pytest.mark.asyncio
async def test_stats_cua_quan_ly_dem_tat_ca(api: AsyncClient, boi_canh: dict[str, object]) -> None:
    response = await api.get("/api/v1/bins/stats", headers=_auth(boi_canh["token_manager"]))

    assert response.status_code == 200, response.text
    assert response.json()["tong"] == 4


@pytest.mark.asyncio
async def test_nhan_vien_mo_duoc_chi_tiet_thung_cua_minh(api: AsyncClient, boi_canh: dict[str, object]) -> None:
    response = await api.get("/api/v1/bins/BIN-A1", headers=_auth(boi_canh["token_a"]))

    assert response.status_code == 200, response.text
    assert response.json()["code"] == "BIN-A1"


@pytest.mark.asyncio
async def test_nhan_vien_khong_mo_duoc_thung_cua_nguoi_khac(api: AsyncClient, boi_canh: dict[str, object]) -> None:
    response = await api.get("/api/v1/bins/BIN-B1", headers=_auth(boi_canh["token_a"]))

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "NF-404"


@pytest.mark.asyncio
async def test_nhan_vien_khong_mo_duoc_thung_chua_gan_ai(api: AsyncClient, boi_canh: dict[str, object]) -> None:
    response = await api.get("/api/v1/bins/BIN-CHUA", headers=_auth(boi_canh["token_a"]))

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "NF-404"


@pytest.mark.asyncio
async def test_cau_loi_404_giong_het_thung_khong_ton_tai(api: AsyncClient, boi_canh: dict[str, object]) -> None:
    """Thùng của người khác và thùng không tồn tại phải không phân biệt được."""
    cua_nguoi_khac = await api.get("/api/v1/bins/BIN-B1", headers=_auth(boi_canh["token_a"]))
    khong_ton_tai = await api.get("/api/v1/bins/BIN-KHONG-CO-THAT", headers=_auth(boi_canh["token_a"]))

    assert cua_nguoi_khac.status_code == 404
    assert khong_ton_tai.status_code == 404
    e_khac = cua_nguoi_khac.json()["error"]
    e_khong = khong_ton_tai.json()["error"]
    assert e_khac["code"] == e_khong["code"] == "NF-404"
    loi_thay_ma = e_khong["message_vi"].replace("BIN-KHONG-CO-THAT", "BIN-B1")
    assert e_khac["message_vi"] == loi_thay_ma, "Chỉ khác mỗi mã thùng trong câu, nếu không thì lộ mã có thật"


@pytest.mark.asyncio
async def test_quan_ly_mo_duoc_thung_chua_gan(api: AsyncClient, boi_canh: dict[str, object]) -> None:
    response = await api.get("/api/v1/bins/BIN-CHUA", headers=_auth(boi_canh["token_manager"]))

    assert response.status_code == 200, response.text
    assert response.json()["assigned_cleaner_id"] is None


@pytest.mark.asyncio
async def test_loc_can_gom_van_ap_dung_theo_nhan_vien(
    api: AsyncClient, api_session: Session, boi_canh: dict[str, object]
) -> None:
    for ma in ("BIN-A1", "BIN-B1"):
        thung = api_session.scalar(select(Bin).where(Bin.code == ma))
        thung.fill_percent = 92.0
    api_session.commit()

    response = await api.get("/api/v1/bins?only_needs_collection=true", headers=_auth(boi_canh["token_a"]))

    assert response.status_code == 200, response.text
    codes = [i["code"] for i in response.json()["items"]]
    assert codes == ["BIN-A1"], "BIN-B1 đầy nhưng là của người khác, không được lọt vào danh sách của A"


@pytest.mark.asyncio
async def test_bo_xep_tuyen_va_diem_gui_cu_dan_khong_bi_loc(
    api: AsyncClient, api_session: Session, boi_canh: dict[str, object]
) -> None:
    """Bộ xếp tuyến và điểm gửi cư dân không được lọc theo ai được giao."""
    for ma in ("BIN-A1", "BIN-B1", "BIN-CHUA"):
        thung = api_session.scalar(select(Bin).where(Bin.code == ma))
        thung.fill_percent = 95.0
    api_session.commit()

    tuyen = bins.thung_can_gom(api_session, datetime.now(UTC))
    codes = sorted(t.code for t in tuyen)
    assert codes == ["BIN-A1", "BIN-B1", "BIN-CHUA"], "Bộ xếp tuyến phải thấy mọi thùng đầy, không lọc theo ai được giao"

    response = await api.get("/api/v1/bins/diem-gui", headers=_auth(boi_canh["token_resident"]))
    assert response.status_code == 200, response.text
    assert len(response.json()["items"]) == 4, "Cư dân phải thấy mọi điểm gửi, không phụ thuộc ai được giao thùng"
