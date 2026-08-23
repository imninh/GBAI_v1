"""Chống phát lại cho đường thiết bị (captures / heartbeat).

Bản không dùng CSDL: chữ ký HMAC-SHA256(khoá, "device_id.timestamp") + cửa sổ
thời gian + bộ nhớ trong tiến trình. Cờ ``IOT_CHONG_PHAT_LAI`` mặc định TẮT —
đường đi giữ nguyên hiện tại.

Test đi qua HTTP thật (AsyncClient / ASGITransport), không gọi thẳng hàm con.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import time
from collections.abc import Iterator
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.deps import get_db
from src.config import get_settings, reset_settings_cache
from src.db.models import Base, Bin, Classification, WasteCategory
from src.main import app
from src.services import device_auth, khoa_thiet_bi
from src.services.classifier_types import ClassifyOutcome

DEVICE_ID = "GBIN-001"
DEVICE_KEY = "test-key-123"
BIN_KEY = "bin-shared-key-123"


def _ky(device_id: str, key: str, ts: int) -> str:
    return hmac.new(key.encode(), f"{device_id}.{ts}".encode(), hashlib.sha256).hexdigest()


@pytest.fixture
def device_keys(monkeypatch):
    """Cấu hình khoá thiết bị đã biết, cờ chống phát lại TẮT (mặc định)."""
    monkeypatch.setenv("IOT_DEVICE_KEYS", f"{DEVICE_ID}:{DEVICE_KEY}")
    monkeypatch.delenv("IOT_CHONG_PHAT_LAI", raising=False)
    get_settings.cache_clear()
    device_auth.reset_cache()
    device_auth.reset_replay_store()
    yield DEVICE_KEY
    get_settings.cache_clear()
    device_auth.reset_cache()


@pytest.fixture
def device_keys_bat(monkeypatch):
    """Cấu hình khoá thiết bị đã biết, cờ chống phát lại BẬT."""
    monkeypatch.setenv("IOT_DEVICE_KEYS", f"{DEVICE_ID}:{DEVICE_KEY}")
    monkeypatch.setenv("IOT_CHONG_PHAT_LAI", "true")
    get_settings.cache_clear()
    device_auth.reset_cache()
    device_auth.reset_replay_store()
    yield DEVICE_KEY
    get_settings.cache_clear()
    device_auth.reset_cache()


@pytest.fixture
def bin_keys(monkeypatch):
    """Khoá chung của thùng (BIN_DEVICE_KEY), cờ chống phát lại TẮT."""
    monkeypatch.setenv("BIN_DEVICE_KEY", BIN_KEY)
    monkeypatch.delenv("IOT_CHONG_PHAT_LAI", raising=False)
    get_settings.cache_clear()
    device_auth.reset_replay_store()
    yield BIN_KEY
    get_settings.cache_clear()
    device_auth.reset_replay_store()


@pytest.fixture
def bin_keys_bat(monkeypatch):
    """Khoá chung của thùng (BIN_DEVICE_KEY), cờ chống phát lại BẬT."""
    monkeypatch.setenv("BIN_DEVICE_KEY", BIN_KEY)
    monkeypatch.setenv("IOT_CHONG_PHAT_LAI", "true")
    get_settings.cache_clear()
    device_auth.reset_replay_store()
    yield BIN_KEY
    get_settings.cache_clear()
    device_auth.reset_replay_store()


@pytest.fixture(autouse=True)
def _lam_sach() -> Iterator[None]:
    """Mỗi test chạy với cấu hình sạch và bộ nhớ chống phát lại rỗng."""
    reset_settings_cache()
    device_auth.reset_replay_store()
    yield
    reset_settings_cache()
    device_auth.reset_replay_store()


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


def _tao_thung(session: Session, **fields: object) -> Bin:
    defaults: dict[str, object] = {
        "code": "BIN-001",
        "name": "Thùng Bờ Hồ",
        "address": "Phố Đinh Tiên Hoàng, Hoàn Kiếm, Hà Nội",
        "lat": 21.0285,
        "lng": 105.8542,
        "fill_percent": 10.0,
        "battery_percent": 100.0,
        "is_active": True,
    }
    defaults.update(fields)
    thung = Bin(**defaults)
    session.add(thung)
    session.flush()
    return thung


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (10, 200, 90)).save(buf, format="JPEG")
    return buf.getvalue()


def _patch_classifier(api_session: Session):
    def _make():
        nhom = api_session.scalar(select(WasteCategory).where(WasteCategory.code == "recyclable_plastic"))
        return ClassifyOutcome(category=nhom, confidence=0.91, refused=False)

    return patch(
        "src.api.iot.classify_waste",
        side_effect=lambda session, image_bytes=None, image_phash="": _make(),
    )


# ─── 1. Cờ tắt (mặc định): request kiểu cũ vẫn 200 ────────────────────────────


@pytest.mark.asyncio
async def test_co_tat_mac_dinh_request_kieu_cu_van_200(api: AsyncClient, device_keys):
    resp = await api.post(
        "/api/v1/iot/heartbeat",
        json={"device_id": DEVICE_ID, "uptime_s": 0},
        headers={"X-Device-Key": DEVICE_KEY},
    )
    assert resp.status_code == 200
    assert resp.json()["device_id"] == DEVICE_ID


# ─── 2. Cờ bật, chữ ký đúng, trong cửa sổ → 200 ───────────────────────────────


@pytest.mark.asyncio
async def test_bat_ky_dung_trong_cua_so_200(api: AsyncClient, device_keys_bat):
    ts = int(time.time())
    resp = await api.post(
        "/api/v1/iot/heartbeat",
        json={"device_id": DEVICE_ID, "uptime_s": 0},
        headers={
            "X-Device-Key": DEVICE_KEY,
            "X-Device-Timestamp": str(ts),
            "X-Device-Signature": _ky(DEVICE_ID, DEVICE_KEY, ts),
        },
    )
    assert resp.status_code == 200


# ─── 3. Cờ bật, phát lại y nguyên → 401 ───────────────────────────────────────


@pytest.mark.asyncio
async def test_bat_phat_lai_y_nguyen_401(api: AsyncClient, device_keys_bat):
    ts = int(time.time())
    headers = {
        "X-Device-Key": DEVICE_KEY,
        "X-Device-Timestamp": str(ts),
        "X-Device-Signature": _ky(DEVICE_ID, DEVICE_KEY, ts),
    }
    payload = {"device_id": DEVICE_ID, "uptime_s": 0}
    lan_1 = await api.post("/api/v1/iot/heartbeat", json=payload, headers=headers)
    assert lan_1.status_code == 200
    lan_2 = await api.post("/api/v1/iot/heartbeat", json=payload, headers=headers)
    assert lan_2.status_code == 401


# ─── 4. Cờ bật, timestamp lệch quá cửa sổ (quá khứ + tương lai) → 401 ────────


@pytest.mark.asyncio
async def test_bat_timestamp_qua_khu_401(api: AsyncClient, device_keys_bat):
    ts = int(time.time()) - 600  # lệch 10 phút về trước
    resp = await api.post(
        "/api/v1/iot/heartbeat",
        json={"device_id": DEVICE_ID, "uptime_s": 0},
        headers={
            "X-Device-Key": DEVICE_KEY,
            "X-Device-Timestamp": str(ts),
            "X-Device-Signature": _ky(DEVICE_ID, DEVICE_KEY, ts),
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_bat_timestamp_tuong_lai_401(api: AsyncClient, device_keys_bat):
    ts = int(time.time()) + 600  # lệch 10 phút về sau
    resp = await api.post(
        "/api/v1/iot/heartbeat",
        json={"device_id": DEVICE_ID, "uptime_s": 0},
        headers={
            "X-Device-Key": DEVICE_KEY,
            "X-Device-Timestamp": str(ts),
            "X-Device-Signature": _ky(DEVICE_ID, DEVICE_KEY, ts),
        },
    )
    assert resp.status_code == 401


# ─── 5. Cờ bật, chữ ký sai → 401, thông báo GIỐNG ca #4 ──────────────────────


@pytest.mark.asyncio
async def test_bat_ky_sai_401_thong_bao_giong_qua_han(
    api: AsyncClient, device_keys_bat
):
    ts = int(time.time())
    resp_sai_ky = await api.post(
        "/api/v1/iot/heartbeat",
        json={"device_id": DEVICE_ID, "uptime_s": 0},
        headers={
            "X-Device-Key": DEVICE_KEY,
            "X-Device-Timestamp": str(ts),
            "X-Device-Signature": "deadbeef" * 8,
        },
    )
    assert resp_sai_ky.status_code == 401, resp_sai_ky.text

    ts_qua_han = int(time.time()) - 600
    resp_qua_han = await api.post(
        "/api/v1/iot/heartbeat",
        json={"device_id": DEVICE_ID, "uptime_s": 0},
        headers={
            "X-Device-Key": DEVICE_KEY,
            "X-Device-Timestamp": str(ts_qua_han),
            "X-Device-Signature": _ky(DEVICE_ID, DEVICE_KEY, ts_qua_han),
        },
    )
    assert resp_qua_han.status_code == 401
    # Cả chữ ký sai và quá hạn đều trả CÙNG một thông báo, không nói rõ sai ở đâu.
    assert resp_sai_ky.json()["error"]["message_vi"] == resp_qua_han.json()["error"]["message_vi"]


# ─── 6. Cờ bật, thiếu hẳn hai header mới → 401 ───────────────────────────────


@pytest.mark.asyncio
async def test_bat_thieu_header_moi_401(api: AsyncClient, device_keys_bat):
    resp = await api.post(
        "/api/v1/iot/heartbeat",
        json={"device_id": DEVICE_ID, "uptime_s": 0},
        headers={"X-Device-Key": DEVICE_KEY},
    )
    assert resp.status_code == 401


# ─── 7. /phien/* vẫn chạy đúng ở cả hai trạng thái cờ ────────────────────────


@pytest.mark.asyncio
async def test_phien_ma_qr_co_tat(api: AsyncClient, api_session: Session, device_keys):
    _tao_thung(api_session, code="BIN-001")
    resp = await api.post(
        "/api/v1/phien/ma-qr",
        json={"bin_code": "BIN-001"},
        headers={"X-Device-Key": DEVICE_KEY},
    )
    assert resp.status_code == 200
    assert "ma" in resp.json()


@pytest.mark.asyncio
async def test_phien_ma_qr_bat(
    api: AsyncClient, api_session: Session, device_keys_bat
):
    _tao_thung(api_session, code="BIN-001")
    resp = await api.post(
        "/api/v1/phien/ma-qr",
        json={"bin_code": "BIN-001"},
        headers={"X-Device-Key": DEVICE_KEY},
    )
    assert resp.status_code == 200
    assert "ma" in resp.json()


# ─── 8. item_id chống trùng vẫn hoạt động (cờ bật, timestamp khác nhau) ────────


@pytest.mark.asyncio
async def test_item_id_idempotent_khi_bat_chong_phat_lai(
    api: AsyncClient, api_session: Session, device_keys_bat
):
    async def _go(ts: int):
        return await api.post(
            "/api/v1/iot/captures",
            files={"image": ("capture.jpg", _jpeg(), "image/jpeg")},
            data={
                "device_id": DEVICE_ID,
                "bin_code": "BIN-001",
                "item_id": "ITEM-GOC",
            },
            headers={
                "X-Device-Key": DEVICE_KEY,
                "X-Device-Timestamp": str(ts),
                "X-Device-Signature": _ky(DEVICE_ID, DEVICE_KEY, ts),
            },
        )

    with _patch_classifier(api_session):
        r1 = await _go(int(time.time()))
        r2 = await _go(int(time.time()) + 1)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["item_id"] == r2.json()["item_id"]

    so_phan_loai = api_session.scalar(select(func.count(Classification.id)))
    assert so_phan_loai == 1


# ─── 9. /bins/{code}/readings cũng được bảo vệ ───────────────────────────────


def _reading_payload(device_id: str = "DEV-READER") -> dict:
    return {
        "fill_percent": 50.0,
        "battery_percent": 90.0,
        "source": "device",
        "device_id": device_id,
    }


@pytest.mark.asyncio
async def test_readings_co_tat_nhu_cu_200(api: AsyncClient, api_session: Session, bin_keys):
    _tao_thung(api_session, code="BIN-001")
    resp = await api.post(
        "/api/v1/bins/BIN-001/readings",
        json=_reading_payload(),
        headers={"X-Device-Key": BIN_KEY},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_readings_bat_phat_lai_401(api: AsyncClient, api_session: Session, bin_keys_bat):
    _tao_thung(api_session, code="BIN-001")
    ts = int(time.time())
    headers = {
        "X-Device-Key": BIN_KEY,
        "X-Device-Timestamp": str(ts),
        "X-Device-Signature": _ky("DEV-READER", BIN_KEY, ts),
    }
    lan_1 = await api.post(
        "/api/v1/bins/BIN-001/readings", json=_reading_payload(), headers=headers
    )
    assert lan_1.status_code == 200
    lan_2 = await api.post(
        "/api/v1/bins/BIN-001/readings", json=_reading_payload(), headers=headers
    )
    assert lan_2.status_code == 401


# ─── 10. Thùng CÓ khoá riêng (device_key_hash) — cờ bật: hợp lệ 200, phát lại 401 ─


@pytest.mark.asyncio
async def test_readings_thung_khoa_rieng_bat_hop_le_roi_phat_lai(
    api: AsyncClient, api_session: Session, bin_keys_bat
):
    """Ca quyết định: thùng có ``device_key_hash`` riêng (phần lớn thùng thật).

    Server không giữ khoá thô trong CSDL (chỉ giữ băm), nhưng thiết bị vừa gửi
    khoá thô trong ``X-Device-Key`` và nó vừa mở được thùng — dùng chính chuỗi
    đó làm khoá HMAC thì tính được chữ ký cho cả nhóm thùng này.
    """
    thung = _tao_thung(api_session, code="BIN-KHOA-RIENG")
    khoa_tho = khoa_thiet_bi.cap_khoa_moi(thung)
    api_session.commit()

    headers = {
        "X-Device-Key": khoa_tho,
        "X-Device-Timestamp": str(int(time.time())),
        "X-Device-Signature": _ky("DEV-READER", khoa_tho, int(time.time())),
    }
    lan_1 = await api.post(
        "/api/v1/bins/BIN-KHOA-RIENG/readings", json=_reading_payload(), headers=headers
    )
    assert lan_1.status_code == 200
    # Gửi lại y nguyên bộ ba (device_id, timestamp, chữ ký) → chặn.
    lan_2 = await api.post(
        "/api/v1/bins/BIN-KHOA-RIENG/readings", json=_reading_payload(), headers=headers
    )
    assert lan_2.status_code == 401


@pytest.mark.asyncio
async def test_readings_thung_khoa_rieng_co_tat_kieu_cu_van_200(
    api: AsyncClient, api_session: Session, bin_keys
):
    """Thùng khoá riêng + cờ TẮT: request kiểu cũ (không header mới) vẫn 200."""
    thung = _tao_thung(api_session, code="BIN-KHOA-RIENG-TAT")
    khoa_tho = khoa_thiet_bi.cap_khoa_moi(thung)
    api_session.commit()
    resp = await api.post(
        "/api/v1/bins/BIN-KHOA-RIENG-TAT/readings",
        json=_reading_payload(),
        headers={"X-Device-Key": khoa_tho},
    )
    assert resp.status_code == 200

