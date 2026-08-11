"""Test khoá thiết bị riêng cho từng thùng thu gom (gói A3a).

Mỗi thùng có thể có một khoá riêng, lưu dạng băm. Thùng chưa cấp khoá riêng thì
vẫn dùng khoá chung để đội thùng ngoài hiện trường không chết giữa chừng.
"""

from __future__ import annotations

import itertools
import re
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.deps import get_db
from src.config import reset_settings_cache
from src.db.models import Base, Bin
from src.db.schema_patch import COT_CAN_VA
from src.main import app
from src.services.khoa_thiet_bi import cap_khoa_moi, kiem_khoa, sinh_khoa, thu_hoi_khoa

KHOI_DEVICE = "khoa-demo-thiet-bi"

_so_thung = itertools.count(1)


@pytest.fixture(autouse=True)
def _xoam_cache_cau_hinh() -> Iterator[None]:
    """Cấu hình đọc qua ``lru_cache`` nên phải xoá cache quanh mỗi test."""
    reset_settings_cache()
    yield
    reset_settings_cache()


def _dat_khoa_thiet_bi(monkeypatch: pytest.MonkeyPatch, gia_tri: str) -> None:
    """Đặt BIN_DEVICE_KEY rồi xoá cache — Settings không đọc lại nếu không xoá."""
    monkeypatch.setenv("BIN_DEVICE_KEY", gia_tri)
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


def _khoi_readings(code: str) -> dict[str, object]:
    return {"fill_percent": 55.0, "battery_percent": 70.0, "source": "device"}


# --- Đường cũ không gãy ------------------------------------------------


@pytest.mark.asyncio
async def test_thung_chua_cap_khoa_van_dung_khoa_chung(
    api: AsyncClient, api_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Thùng chưa cấp khoá riêng (``device_key_hash == ''``) vẫn mở bằng khoá chung."""
    _dat_khoa_thiet_bi(monkeypatch, KHOI_DEVICE)
    thung = _tao_thung(api_session)
    api_session.commit()
    assert thung.device_key_hash == ""

    response = await api.post(
        f"/api/v1/bins/{thung.code}/readings",
        json=_khoi_readings(thung.code),
        headers={"X-Device-Key": KHOI_DEVICE},
    )

    assert response.status_code == 200, response.text


# --- Khoá riêng --------------------------------------------------------


@pytest.mark.asyncio
async def test_thung_da_cap_khoa_thi_khoa_rieng_mo_duoc(
    api: AsyncClient, api_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _dat_khoa_thiet_bi(monkeypatch, KHOI_DEVICE)
    thung = _tao_thung(api_session)
    khoa = cap_khoa_moi(thung)
    api_session.commit()

    response = await api.post(
        f"/api/v1/bins/{thung.code}/readings",
        json=_khoi_readings(thung.code),
        headers={"X-Device-Key": khoa},
    )

    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_thung_da_cap_khoa_thi_khoa_CHUNG_khong_mo_duoc(  # noqa: N802 — tên do gói quy định
    api: AsyncClient, api_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Thùng đã cấp khoá riêng thì khoá chung KHÔNG mở được — đây là test quan
    trọng nhất của gói: cấp khoá riêng mà khoá chung vẫn vào được thì chẳng thu
    hẹp được gì."""
    _dat_khoa_thiet_bi(monkeypatch, KHOI_DEVICE)
    thung = _tao_thung(api_session)
    cap_khoa_moi(thung)
    api_session.commit()

    response = await api.post(
        f"/api/v1/bins/{thung.code}/readings",
        json=_khoi_readings(thung.code),
        headers={"X-Device-Key": KHOI_DEVICE},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "BIN-KEY-401"


@pytest.mark.asyncio
async def test_khoa_cua_thung_khac_khong_mo_duoc(
    api: AsyncClient, api_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _dat_khoa_thiet_bi(monkeypatch, KHOI_DEVICE)
    thung_a = _tao_thung(api_session, code="BIN-A")
    thung_b = _tao_thung(api_session, code="BIN-B")
    khoa_a = cap_khoa_moi(thung_a)
    cap_khoa_moi(thung_b)
    api_session.commit()

    response = await api.post(
        f"/api/v1/bins/{thung_b.code}/readings",
        json=_khoi_readings(thung_b.code),
        headers={"X-Device-Key": khoa_a},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "BIN-KEY-401"


@pytest.mark.asyncio
async def test_khoa_rong_bi_chan(
    api: AsyncClient, api_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Không gửi header → chặn, kể cả với thùng chưa cấp khoá riêng. Fail closed."""
    _dat_khoa_thiet_bi(monkeypatch, KHOI_DEVICE)
    thung = _tao_thung(api_session)
    api_session.commit()

    response = await api.post(f"/api/v1/bins/{thung.code}/readings", json=_khoi_readings(thung.code))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "BIN-KEY-401"


@pytest.mark.asyncio
async def test_cap_lai_khoa_thu_hoi_khoa_cu(
    api: AsyncClient, api_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _dat_khoa_thiet_bi(monkeypatch, KHOI_DEVICE)
    thung = _tao_thung(api_session)
    khoa_cu = cap_khoa_moi(thung)
    khoa_moi = cap_khoa_moi(thung)
    api_session.commit()
    duong = f"/api/v1/bins/{thung.code}/readings"
    json_body = _khoi_readings(thung.code)

    cu = await api.post(duong, json=json_body, headers={"X-Device-Key": khoa_cu})
    moi = await api.post(duong, json=json_body, headers={"X-Device-Key": khoa_moi})

    assert cu.status_code == 401, "Cấp lại là thu hồi: khoá cũ phải chết từ request kế tiếp"
    assert moi.status_code == 200, moi.text


# --- Không bao giờ lưu khoá thô ----------------------------------------


@pytest.mark.asyncio
async def test_khong_bao_gio_luu_khoa_tho(api_session: Session) -> None:
    thung = _tao_thung(api_session)
    khoa = cap_khoa_moi(thung)
    api_session.commit()

    assert thung.device_key_hash != khoa, "Không được lưu chuỗi khoá thô"
    assert re.fullmatch(r"[0-9a-f]{64}", thung.device_key_hash), "Phải là băm SHA-256: 64 ký tự hex"


@pytest.mark.asyncio
async def test_hai_lan_sinh_khoa_khac_nhau() -> None:
    cac_khoa = {sinh_khoa() for _ in range(50)}

    assert len(cac_khoa) == 50, "50 lần sinh phải cho 50 khoá khác nhau"
    assert all(len(khoa) >= 32 for khoa in cac_khoa)


# --- Chốt chặn hạ tầng -------------------------------------------------


@pytest.mark.asyncio
async def test_cot_duoc_khai_trong_cot_can_va() -> None:
    assert any(bang == "bins" and cot == "device_key_hash" for bang, cot, _ in COT_CAN_VA), (
        "Quên khai cột trong COT_CAN_VA là production thiếu cột trong khi test vẫn xanh"
    )


# --- Thu hồi khoá (gói A3c) ---------------------------------------------


@pytest.mark.asyncio
async def test_thu_hoi_roi_thi_khoa_cu_khong_mo_duoc(api_session: Session) -> None:
    thung = _tao_thung(api_session)
    khoa_cu = cap_khoa_moi(thung)
    thu_hoi_khoa(thung)
    api_session.commit()

    assert kiem_khoa(thung, khoa_cu, "") is False, "Khoá cũ phải chết sau khi thu hồi"


@pytest.mark.asyncio
async def test_thu_hoi_roi_thi_khoa_chung_cung_khong_mo_duoc(api_session: Session) -> None:
    """Chốt chặn quan trọng nhất: thu hồi KHÔNG được làm thùng rơi về khoá chung.

    Nếu `thu_hoi_khoa` đặt `device_key_hash = ""` thì `kiem_khoa` sẽ rơi về nhánh
    "thùng chưa cấp khoá riêng" và so với khoá chung — thùng vừa bị lộ khoá lại
    mở bằng chính cơ chế lỏng hơn. Thùng thu hồi phải chặn CẢ khoá chung.
    """
    thung = _tao_thung(api_session)
    cap_khoa_moi(thung)
    thu_hoi_khoa(thung)
    api_session.commit()

    assert kiem_khoa(thung, KHOI_DEVICE, KHOI_DEVICE) is False, (
        "Thu hồi xong mà khoá chung vẫn mở được là hạ cấp bảo mật"
    )


@pytest.mark.asyncio
async def test_thu_hoi_roi_cap_lai_thi_mo_duoc_bang_khoa_moi(api_session: Session) -> None:
    thung = _tao_thung(api_session)
    khoa_cu = cap_khoa_moi(thung)
    thu_hoi_khoa(thung)
    khoa_moi = cap_khoa_moi(thung)
    api_session.commit()

    assert kiem_khoa(thung, khoa_moi, "") is True, "Khoá mới cấp sau thu hồi phải mở được"
    assert kiem_khoa(thung, khoa_cu, "") is False, "Khoá trước thu hồi vẫn phải chết"


@pytest.mark.asyncio
async def test_thu_hoi_khong_dung_toi_thung_khac(api_session: Session) -> None:
    thung_a = _tao_thung(api_session, code="BIN-01")
    thung_b = _tao_thung(api_session, code="BIN-02")
    khoa_a = cap_khoa_moi(thung_a)
    cap_khoa_moi(thung_b)
    bam_b_truoc = thung_b.device_key_hash
    api_session.commit()

    thu_hoi_khoa(thung_a)
    api_session.commit()

    assert thung_b.device_key_hash == bam_b_truoc, "Thu hồi BIN-01 không được đụng BIN-02"
    assert kiem_khoa(thung_a, khoa_a, "") is False, "Khoá BIN-01 đã bị thu hồi"
