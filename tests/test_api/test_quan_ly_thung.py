"""Ban quản lý thêm / sửa / ngừng dùng thùng — gói P31 (nửa GHI của bản đồ thùng).

Trước gói này không có đường nào tạo thùng: mọi thùng đều sinh ra từ
``scripts/seed.py`` chạy tay. Bốn endpoint mới (POST/PATCH/DELETE + kich-hoat)
đi qua quyền ``manage_bins`` (chỉ manager), mọi thao tác ghi đều để lại
``AuditLog``, và việc "ngừng dùng" là tắt cờ ``is_active`` chứ KHÔNG xoá hàng —
xoá hàng là xoá luôn lịch sử readings (cascade delete-orphan) và làm hỏng hồ sơ
tuyến cũ còn tham chiếu ``bin_id``.

Không test nào chạm mạng: ASGI transport chạy thẳng trên app trong bộ nhớ.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.deps import get_db
from src.config import reset_settings_cache
from src.db.models import (
    STOP_KIND_THUNG,
    AuditLog,
    Base,
    Bin,
    BinReading,
    PickupRoute,
    RouteStop,
)
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
        "code": f"BIN-P31-{next(_so_thung):03d}",
        "name": "Thùng thử nghiệm",
        "address": "Phố Đinh Tiên Hoàng, Hoàn Kiếm, Hà Nội",
        "lat": 21.0285,
        "lng": 105.8542,
        "category_codes": ["recyclable_paper"],
        "capacity_liters": 660.0,
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


def _payload_tao(code: str) -> dict:
    return {
        "code": code,
        "name": "Thùng mới",
        "address": "Phố Hàng Bài, Hoàn Kiếm, Hà Nội",
        "lat": 21.0285,
        "lng": 105.8542,
        "category_codes": ["recyclable_paper"],
        "capacity_liters": 500.0,
    }


# --- Quyền (4) ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_cu_dan_khong_tao_duoc_thung(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "resident@demo.vn")
    response = await api.post("/api/v1/bins", json=_payload_tao("BIN-CU-DAN"), headers=_auth(token))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_nhan_vien_khong_tao_duoc_thung(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "cleaner@demo.vn")
    response = await api.post("/api/v1/bins", json=_payload_tao("BIN-NV"), headers=_auth(token))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_khong_token_thi_401(api: AsyncClient) -> None:
    response = await api.post("/api/v1/bins", json=_payload_tao("BIN-KHONG-TOKEN"))
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_quan_ly_tao_duoc_thung(api: AsyncClient, api_session: Session) -> None:
    token = await _dang_nhap(api, "manager@demo.vn")
    response = await api.post("/api/v1/bins", json=_payload_tao("BIN-TAO-01"), headers=_auth(token))
    assert response.status_code == 201, response.text
    du_lieu = response.json()
    assert du_lieu["code"] == "BIN-TAO-01"
    assert du_lieu["name"] == "Thùng mới"

    danh_sach = (await api.get("/api/v1/bins", headers=_auth(token))).json()["items"]
    assert any(t["code"] == "BIN-TAO-01" for t in danh_sach), "Thùng mới phải có mặt trong GET /bins"


# --- Kiểm dữ liệu (4) ---------------------------------------------------------


@pytest.mark.asyncio
async def test_ma_thung_trung_bi_tu_choi(api: AsyncClient, api_session: Session) -> None:
    _tao_thung(api_session, code="BIN-DUP-01")
    api_session.commit()
    token = await _dang_nhap(api, "manager@demo.vn")

    response = await api.post("/api/v1/bins", json=_payload_tao("BIN-DUP-01"), headers=_auth(token))

    assert response.status_code == 400, response.text
    assert "duy nhất" in response.json()["error"]["message_vi"]


@pytest.mark.asyncio
async def test_toa_do_ngoai_khoang_bi_tu_choi(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "manager@demo.vn")
    payload = _payload_tao("BIN-LAT-200")
    payload["lat"] = 200.0

    response = await api.post("/api/v1/bins", json=payload, headers=_auth(token))

    assert response.status_code == 400, response.text
    assert "vĩ độ" in response.json()["error"]["message_vi"]


@pytest.mark.asyncio
async def test_ma_nhom_rac_khong_ton_tai_bi_tu_choi(api: AsyncClient) -> None:
    token = await _dang_nhap(api, "manager@demo.vn")
    payload = _payload_tao("BIN-RAC-LA")
    payload["category_codes"] = ["khong-ton-tai"]

    response = await api.post("/api/v1/bins", json=payload, headers=_auth(token))

    assert response.status_code == 400, response.text
    assert "khong-ton-tai" in response.json()["error"]["message_vi"]


@pytest.mark.asyncio
async def test_sua_khong_dung_toi_truong_khong_truyen(api: AsyncClient, api_session: Session) -> None:
    thung = _tao_thung(api_session, code="BIN-PATCH-1")
    api_session.commit()
    token = await _dang_nhap(api, "manager@demo.vn")

    response = await api.patch(
        f"/api/v1/bins/{thung.code}",
        json={"name": "Thùng đã đổi tên"},
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    du_lieu = response.json()
    assert du_lieu["name"] == "Thùng đã đổi tên"
    assert du_lieu["address"] == thung.address, "Chỉ gửi name thì address không được đổi"
    assert du_lieu["lat"] == thung.lat, "Chỉ gửi name thì toạ độ không được đổi"
    assert du_lieu["lng"] == thung.lng


# --- Ranh giới (4) ------------------------------------------------------------


@pytest.mark.asyncio
async def test_khong_sua_duoc_muc_day_va_pin(api: AsyncClient, api_session: Session) -> None:
    """Số đo thiết bị không được sửa tay.

    ``fill_percent``/``battery_percent``/``last_seen_at`` là con số thiết bị báo
    về — người quản lý gõ vào là bịa số đo, nuôi quyết định điều phối bằng dữ
    liệu giả. Gửi kèm trong PATCH phải bị bỏ qua, giá trị không đổi.
    """
    thung = _tao_thung(api_session, code="BIN-FILL-1", fill_percent=50.0, battery_percent=60.0)
    api_session.commit()
    token = await _dang_nhap(api, "manager@demo.vn")

    response = await api.patch(
        f"/api/v1/bins/{thung.code}",
        json={"name": "Đổi tên", "fill_percent": 99.0, "battery_percent": 1.0},
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    du_lieu = response.json()
    assert du_lieu["name"] == "Đổi tên"
    assert du_lieu["fill_percent"] == 50.0, "fill_percent không được đổi bằng tay"
    assert du_lieu["battery_percent"] == 60.0, "battery_percent không được đổi bằng tay"


@pytest.mark.asyncio
async def test_ngung_dung_giu_lai_lich_su_readings(api: AsyncClient, api_session: Session) -> None:
    """Chốt chặn chính: ngừng dùng là tắt cờ chứ KHÔNG xoá hàng.

    Nếu dùng ``session.delete`` thì ``cascade="all, delete-orphan"`` xoá sạch
    lịch sử readings và làm hỏng hồ sơ tuyến cũ — test này bắt đúng chuyện đó.
    """
    thung = _tao_thung(api_session, code="BIN-DEACT-1")
    for i in range(3):
        api_session.add(
            BinReading(
                bin_id=thung.id,
                fill_percent=float(i * 10),
                battery_percent=100.0,
                source="simulator",
                created_at=datetime.now(UTC),
            )
        )
    api_session.commit()
    token = await _dang_nhap(api, "manager@demo.vn")

    response = await api.delete(f"/api/v1/bins/{thung.code}", headers=_auth(token))

    assert response.status_code == 200, response.text
    api_session.expire_all()
    con_lai = api_session.scalar(select(func.count(BinReading.id)).where(BinReading.bin_id == thung.id))
    assert con_lai == 3, "3 BinReading phải còn nguyên sau khi ngừng dùng thùng"
    thung_sau = api_session.scalar(select(Bin).where(Bin.code == thung.code))
    assert thung_sau is not None, "Thùng phải vẫn tra được theo code sau khi ngừng dùng"
    assert thung_sau.is_active is False, "Ngừng dùng = tắt is_active, không xoá hàng"


@pytest.mark.asyncio
async def test_thung_dang_trong_tuyen_chua_xong_thi_khong_ngung_duoc(
    api: AsyncClient, api_session: Session
) -> None:
    thung = _tao_thung(api_session, code="BIN-TUYEN-1")
    tuyen = PickupRoute(service_date=date(2026, 8, 20), window="sang")
    api_session.add(tuyen)
    api_session.flush()
    api_session.add(RouteStop(route_id=tuyen.id, stop_kind=STOP_KIND_THUNG, bin_id=thung.id, seq=1))
    api_session.commit()
    token = await _dang_nhap(api, "manager@demo.vn")

    response = await api.delete(f"/api/v1/bins/{thung.code}", headers=_auth(token))

    assert response.status_code == 400, response.text
    assert str(tuyen.id) in response.json()["error"]["message_vi"], "Lỗi phải nêu đúng mã tuyến giữ thùng"
    api_session.expire_all()
    assert api_session.scalar(select(Bin).where(Bin.code == thung.code)).is_active is True


@pytest.mark.asyncio
async def test_moi_thao_tac_deu_ghi_audit_log(api: AsyncClient, api_session: Session) -> None:
    dem_truoc = int(api_session.scalar(select(func.count(AuditLog.id))) or 0)
    token = await _dang_nhap(api, "manager@demo.vn")

    tao = await api.post("/api/v1/bins", json=_payload_tao("BIN-AUDIT-1"), headers=_auth(token))
    assert tao.status_code == 201, tao.text
    sua = await api.patch(
        "/api/v1/bins/BIN-AUDIT-1",
        json={"name": "Thùng đã đổi tên lần nữa"},
        headers=_auth(token),
    )
    assert sua.status_code == 200, sua.text
    ngung = await api.delete("/api/v1/bins/BIN-AUDIT-1", headers=_auth(token))
    assert ngung.status_code == 200, ngung.text

    dem_sau = int(api_session.scalar(select(func.count(AuditLog.id))) or 0)
    assert dem_sau - dem_truoc == 3, "Tạo + sửa + ngừng dùng phải ghi đúng 3 dòng nhật ký"

    dong_sua = api_session.scalar(select(AuditLog).where(AuditLog.action == "update_bin"))
    assert dong_sua is not None
    assert dong_sua.entity == "bin"
    assert dong_sua.entity_id == "BIN-AUDIT-1"
    assert dong_sua.detail["truoc"]["name"] != dong_sua.detail["sau"]["name"], "Nhật ký sửa phải ghi trước ≠ sau"
