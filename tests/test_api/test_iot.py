"""Tests for the IoT device API: auth, upload, privacy pipeline, bin readings."""

import io
from collections import Counter
from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.deps import get_db
from src.config import get_settings, reset_settings_cache
from src.db.models import Base, Bin, BinReading
from src.main import app
from src.models.schemas import ClassifyOutcome
from src.services import bin_readings, device_auth
from src.services.khoa_thiet_bi import cap_khoa_moi

DEVICE_ID = "GBIN-001"
DEVICE_KEY = "test-key-123"
KHOI_CHUNG = "khoa-chung-demo"


@pytest.fixture
def device_keys(monkeypatch):
    """Configure a known device key and reset both settings caches."""
    monkeypatch.setenv("IOT_DEVICE_KEYS", f"{DEVICE_ID}:{DEVICE_KEY}")
    get_settings.cache_clear()
    device_auth.reset_cache()
    yield DEVICE_KEY
    get_settings.cache_clear()
    device_auth.reset_cache()


@pytest.fixture(autouse=True)
def _xoam_cache_cau_hinh() -> Iterator[None]:
    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture
def api_session(monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    """CSDL trong bộ nhớ đã seed danh mục, gắn vào dependency của app."""
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


@pytest.fixture(autouse=True)
def clean_readings():
    bin_readings.get_repository().clear()
    yield
    bin_readings.get_repository().clear()


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


def make_jpeg(width: int = 800, height: int = 600, with_exif: bool = True) -> bytes:
    image = Image.new("RGB", (width, height), (120, 200, 90))
    buffer = io.BytesIO()
    if with_exif:
        exif = image.getexif()
        exif[271] = "TestCameraMake"  # Make
        exif[272] = "TestCameraModel"  # Model
        image.save(buffer, format="JPEG", exif=exif)
    else:
        image.save(buffer, format="JPEG")
    return buffer.getvalue()


def upload_files(jpeg: bytes):
    return {"image": ("capture.jpg", jpeg, "image/jpeg")}


def upload_data(fill_percent=None):
    data = {
        "device_id": DEVICE_ID,
        "bin_code": "BIN-001",
        "event_type": "waste_detected",
        "uptime_s": "120",
    }
    if fill_percent is not None:
        data["fill_percent"] = str(fill_percent)
    return data


@pytest.fixture
def mock_classifier():
    """Replace the model call, keeping the real privacy pipeline in the path."""
    outcome = ClassifyOutcome(
        status="ok", label="plastic", confidence=0.91, requires_review=False,
        message="Classified",
    )
    with patch(
        "src.api.iot.classify_processed_image", new=AsyncMock(return_value=outcome)
    ) as mocked:
        yield mocked


# ─── Device authentication (spec §21) ────────────────────────────────────────


@pytest.mark.asyncio
async def test_capture_with_valid_device_key(client, device_keys, mock_classifier):
    response = await client.post(
        "/api/v1/iot/captures",
        files=upload_files(make_jpeg()),
        data=upload_data(),
        headers={"X-Device-Key": DEVICE_KEY},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["label"] == "plastic"
    assert body["confidence"] == pytest.approx(0.91)


@pytest.mark.asyncio
async def test_capture_with_invalid_device_key(client, device_keys, mock_classifier):
    response = await client.post(
        "/api/v1/iot/captures",
        files=upload_files(make_jpeg()),
        data=upload_data(),
        headers={"X-Device-Key": "wrong-key"},
    )
    assert response.status_code == 401
    mock_classifier.assert_not_awaited()  # never reached the model


@pytest.mark.asyncio
async def test_capture_with_missing_device_key(client, device_keys, mock_classifier):
    response = await client.post(
        "/api/v1/iot/captures",
        files=upload_files(make_jpeg()),
        data=upload_data(),
    )
    assert response.status_code == 401
    mock_classifier.assert_not_awaited()


@pytest.mark.asyncio
async def test_device_cannot_post_as_another_device(client, device_keys, mock_classifier):
    data = upload_data()
    data["device_id"] = "GBIN-999"
    response = await client.post(
        "/api/v1/iot/captures",
        files=upload_files(make_jpeg()),
        data=data,
        headers={"X-Device-Key": DEVICE_KEY},
    )
    assert response.status_code == 401


# ─── Image upload and validation ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_capture_runs_privacy_pipeline(client, device_keys, mock_classifier):
    response = await client.post(
        "/api/v1/iot/captures",
        files=upload_files(make_jpeg(1600, 1200)),
        data=upload_data(),
        headers={"X-Device-Key": DEVICE_KEY},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["exif_stripped"] is True
    assert body["phash"]
    assert body["image_bytes"] > 0
    # faces_blurred is an int when detection ran, None when it could not.
    assert body["faces_blurred"] is None or isinstance(body["faces_blurred"], int)


@pytest.mark.asyncio
async def test_capture_rejects_invalid_image(client, device_keys, mock_classifier):
    response = await client.post(
        "/api/v1/iot/captures",
        files={"image": ("capture.jpg", b"this is not an image", "image/jpeg")},
        data=upload_data(),
        headers={"X-Device-Key": DEVICE_KEY},
    )
    assert response.status_code == 422
    mock_classifier.assert_not_awaited()  # garbage never reaches the model


@pytest.mark.asyncio
async def test_capture_rejects_empty_upload(client, device_keys, mock_classifier):
    response = await client.post(
        "/api/v1/iot/captures",
        files={"image": ("capture.jpg", b"", "image/jpeg")},
        data=upload_data(),
        headers={"X-Device-Key": DEVICE_KEY},
    )
    assert response.status_code == 422


# ─── Classifier reuse (spec §9 — no separate IoT classifier) ─────────────────


@pytest.mark.asyncio
async def test_iot_capture_goes_through_the_shared_langgraph_classifier(
    client, device_keys
):
    """The IoT path must use the same graph as every other image source."""
    with patch("src.services.classification.classify_agent") as agent:
        agent.ainvoke = AsyncMock(
            return_value={
                "outcome": ClassifyOutcome(
                    status="ok", label="paper", confidence=0.88
                )
            }
        )
        response = await client.post(
            "/api/v1/iot/captures",
            files=upload_files(make_jpeg()),
            data=upload_data(),
            headers={"X-Device-Key": DEVICE_KEY},
        )

    assert response.status_code == 200
    assert response.json()["label"] == "paper"
    agent.ainvoke.assert_awaited_once()
    # And it received a preprocessed image, not the raw upload.
    payload = agent.ainvoke.await_args.args[0]
    assert payload["source"] == "iot"
    assert payload["image_b64"]
    assert payload["phash"]


# ─── Uncertain results (spec §11) ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_low_confidence_is_reported_as_warning(client, device_keys):
    outcome = ClassifyOutcome(
        status="warning", label="plastic", confidence=0.22, requires_review=True,
        message="Low confidence",
    )
    with patch("src.api.iot.classify_processed_image", new=AsyncMock(return_value=outcome)):
        response = await client.post(
            "/api/v1/iot/captures",
            files=upload_files(make_jpeg()),
            data=upload_data(),
            headers={"X-Device-Key": DEVICE_KEY},
        )
    body = response.json()
    assert body["status"] == "warning"
    assert body["requires_review"] is True


@pytest.mark.asyncio
async def test_refused_result_carries_no_label(client, device_keys):
    outcome = ClassifyOutcome(
        status="refused", label="", confidence=0.0, requires_review=True,
        message="Model returned no label",
    )
    with patch("src.api.iot.classify_processed_image", new=AsyncMock(return_value=outcome)):
        response = await client.post(
            "/api/v1/iot/captures",
            files=upload_files(make_jpeg()),
            data=upload_data(),
            headers={"X-Device-Key": DEVICE_KEY},
        )
    body = response.json()
    assert body["status"] == "refused"
    assert body["label"] == ""


# ─── Bin readings (spec §14) ─────────────────────────────────────────────────


def _dat_khoa_thiet_bi(monkeypatch: pytest.MonkeyPatch, gia_tri: str) -> None:
    """Đặt BIN_DEVICE_KEY rồi xoá cache — Settings không đọc lại nếu không xoá."""
    monkeypatch.setenv("BIN_DEVICE_KEY", gia_tri)
    reset_settings_cache()


@pytest.mark.asyncio
async def test_bin_reading_firmware_khuon_ghi_xuong_csdl(
    api: AsyncClient, api_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Firmware gửi đúng khuôn (có `device_id`) + khoá đúng → GHI xuống CSDL thật.

    Gói P58 gộp ngã ba xác thực: firmware (luôn gửi ``device_id``) trước đây rơi
    vào nhánh ``device_auth`` + kho trong bộ nhớ — giờ chạy đúng một cửa
    ``khoa_thiet_bi`` + ``bins.ghi_nhan_reading``, nên đọc lại từ bảng
    ``bin_readings`` phải thấy bản ghi.
    """
    _dat_khoa_thiet_bi(monkeypatch, KHOI_CHUNG)
    thung = _tao_thung(api_session, code="BIN-001")
    api_session.commit()

    response = await api.post(
        "/api/v1/bins/BIN-001/readings",
        json={"device_id": DEVICE_ID, "fill_percent": 84.5, "is_full": True, "uptime_s": 900},
        headers={"X-Device-Key": KHOI_CHUNG},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["code"] == "BIN-001"
    assert body["fill_percent"] == pytest.approx(84.5)

    hang = api_session.scalar(select(BinReading).where(BinReading.bin_id == thung.id))
    assert hang is not None, "Reading phải nằm trong bảng bin_readings của CSDL"
    assert hang.fill_percent == pytest.approx(84.5)
    assert hang.source == "device"


@pytest.mark.asyncio
async def test_bin_reading_khoa_sai_tra_401(
    api: AsyncClient, api_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _dat_khoa_thiet_bi(monkeypatch, KHOI_CHUNG)
    _tao_thung(api_session, code="BIN-001")
    api_session.commit()

    response = await api.post(
        "/api/v1/bins/BIN-001/readings",
        json={"device_id": DEVICE_ID, "fill_percent": 50.0, "is_full": False},
        headers={"X-Device-Key": "khoa-sai"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "BIN-KEY-401"


@pytest.mark.asyncio
async def test_bin_reading_khoa_thung_khac_khong_bao_cho_thung_kia(
    api: AsyncClient, api_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Khoá của thùng A không báo được cho thùng B — ràng theo `code` trên đường dẫn.

    Mỗi thùng có ``device_key_hash`` riêng (cấp bằng ``cap_khoa_moi``), nên khoá
    hợp lệ của thùng A không mở được thùng B: ``kiem_khoa`` so băm khoá gửi lên
    với băm của ĐÚNG thùng tra theo ``code``.
    """
    _dat_khoa_thiet_bi(monkeypatch, KHOI_CHUNG)
    thung_a = _tao_thung(api_session, code="BIN-A")
    thung_b = _tao_thung(api_session, code="BIN-B")
    khoa_a = cap_khoa_moi(thung_a)
    cap_khoa_moi(thung_b)
    api_session.commit()

    response = await api.post(
        f"/api/v1/bins/{thung_b.code}/readings",
        json={"device_id": DEVICE_ID, "fill_percent": 50.0, "is_full": False},
        headers={"X-Device-Key": khoa_a},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "BIN-KEY-401"
    hang = api_session.scalar(select(BinReading).where(BinReading.bin_id == thung_b.id))
    assert hang is None, "Không được ghi reading vào thùng B bằng khoá của thùng A"


@pytest.mark.asyncio
async def test_bin_reading_requires_device_key(
    api: AsyncClient, api_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _dat_khoa_thiet_bi(monkeypatch, KHOI_CHUNG)
    _tao_thung(api_session, code="BIN-001")
    api_session.commit()

    response = await api.post(
        "/api/v1/bins/BIN-001/readings",
        json={"device_id": DEVICE_ID, "fill_percent": 50.0, "is_full": False},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "BIN-KEY-401"


@pytest.mark.asyncio
@pytest.mark.parametrize("fill_percent", [-1.0, 100.1, 1000.0])
async def test_bin_reading_rejects_out_of_range_fill(
    api: AsyncClient, api_session: Session, monkeypatch: pytest.MonkeyPatch, fill_percent
) -> None:
    """Mức rác ngoài 0–100 không thể vào CSDL (spec §13)."""
    _dat_khoa_thiet_bi(monkeypatch, KHOI_CHUNG)
    _tao_thung(api_session, code="BIN-001")
    api_session.commit()

    response = await api.post(
        "/api/v1/bins/BIN-001/readings",
        json={"device_id": DEVICE_ID, "fill_percent": fill_percent, "is_full": False},
        headers={"X-Device-Key": KHOI_CHUNG},
    )

    assert response.status_code == 400, response.text


@pytest.mark.asyncio
async def test_bin_readings_ghi_xuong_csdl_theo_thu_tu(
    api: AsyncClient, api_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _dat_khoa_thiet_bi(monkeypatch, KHOI_CHUNG)
    thung = _tao_thung(api_session, code="BIN-001")
    api_session.commit()

    for percent in (20.0, 55.0, 88.0):
        response = await api.post(
            "/api/v1/bins/BIN-001/readings",
            json={"device_id": DEVICE_ID, "fill_percent": percent, "is_full": percent >= 80},
            headers={"X-Device-Key": KHOI_CHUNG},
        )
        assert response.status_code == 200, response.text

    cac_hang = api_session.scalars(
        select(BinReading).where(BinReading.bin_id == thung.id).order_by(BinReading.created_at)
    ).all()
    assert [h.fill_percent for h in cac_hang] == [20.0, 55.0, 88.0]


# ─── Heartbeat (spec §21) ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_heartbeat_confirms_backend_is_reachable(client, device_keys):
    """IoT Checkpoint 1 §21 — the device's only way to prove the backend answers."""
    response = await client.post(
        "/api/v1/iot/heartbeat",
        json={"device_id": DEVICE_ID, "status": "online"},
        headers={"X-Device-Key": DEVICE_KEY},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["device_id"] == DEVICE_ID
    assert body["server_time"]


@pytest.mark.asyncio
async def test_heartbeat_requires_device_key(client, device_keys):
    response = await client.post(
        "/api/v1/iot/heartbeat",
        json={"device_id": DEVICE_ID, "status": "online"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_heartbeat_rejects_a_device_impersonating_another(client, device_keys):
    """A valid key for one bin must not let it report as a different bin."""
    response = await client.post(
        "/api/v1/iot/heartbeat",
        json={"device_id": "GBIN-999", "status": "online"},
        headers={"X-Device-Key": DEVICE_KEY},
    )
    assert response.status_code == 401


# ─── Chống tái phát: không được có hai route trùng (method, path) ──────────────


def test_khong_duong_dang_ky_hai_lan():
    """Sau khi gộp repo, `/bins/{code}/readings` từng bị đăng ký ở CẢ `iot.py`
    lẫn `routers/bins.py` — bản sau (iot.py) không bao giờ chạy nhưng vẫn nằm
    trong bảng route, nên gỡ lỗi đi theo đường chết. Chốt: không cặp
    (method, path) nào được xuất hiện hai lần."""
    from src.main import app

    dem = Counter(
        (phuong_thuc, route.path)
        for route in app.routes
        for phuong_thuc in getattr(route, "methods", []) or []
    )
    trung = {cap: so for cap, so in dem.items() if so > 1}
    assert trung == {}, f"Route bị đăng ký hai lần: {trung}"
