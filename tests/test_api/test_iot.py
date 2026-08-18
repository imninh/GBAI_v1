"""Tests for the IoT device API: auth, upload, privacy pipeline, bin readings."""

import io
from collections import Counter
from collections.abc import Iterator
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.deps import get_db
from src.config import get_settings, reset_settings_cache
from src.db.models import Base, Bin, BinReading, WasteCategory
from src.main import app
from src.services import bin_readings, device_auth
from src.services.classifier_types import ClassifyOutcome
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
def mock_classifier(api_session):
    """Replace the 4-tier classifier with a canned outcome — no model, no network.

    `classify_waste` is the 4-tier pipeline (P61); the IoT endpoint now runs it
    and writes Media + Classification to the DB, so the fixture must run inside a
    real session (api_session) that has the waste categories seeded.
    """

    def _make_outcome(code: str = "recyclable_plastic", confidence: float = 0.91, refused: bool = False):
        nhom = api_session.scalar(select(WasteCategory).where(WasteCategory.code == code))
        return ClassifyOutcome(category=nhom, confidence=confidence, refused=refused)

    with patch(
        "src.api.iot.classify_waste",
        side_effect=lambda session, image_bytes=None, image_phash="": _make_outcome(),
    ) as mocked:
        yield mocked


# ─── Device authentication (spec §21) ────────────────────────────────────────


@pytest.mark.asyncio
async def test_capture_with_valid_device_key(api: AsyncClient, api_session: Session, device_keys, mock_classifier):
    response = await api.post(
        "/api/v1/iot/captures",
        files=upload_files(make_jpeg()),
        data=upload_data(),
        headers={"X-Device-Key": DEVICE_KEY},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["label"] == "recyclable_plastic"
    assert body["confidence"] == pytest.approx(0.91)


@pytest.mark.asyncio
async def test_capture_with_invalid_device_key(api: AsyncClient, api_session: Session, device_keys, mock_classifier):
    response = await api.post(
        "/api/v1/iot/captures",
        files=upload_files(make_jpeg()),
        data=upload_data(),
        headers={"X-Device-Key": "wrong-key"},
    )
    assert response.status_code == 401
    mock_classifier.assert_not_called()  # never reached the model


@pytest.mark.asyncio
async def test_capture_with_missing_device_key(api: AsyncClient, api_session: Session, device_keys, mock_classifier):
    response = await api.post(
        "/api/v1/iot/captures",
        files=upload_files(make_jpeg()),
        data=upload_data(),
    )
    assert response.status_code == 401
    mock_classifier.assert_not_called()


@pytest.mark.asyncio
async def test_device_cannot_post_as_another_device(api: AsyncClient, api_session: Session, device_keys, mock_classifier):
    data = upload_data()
    data["device_id"] = "GBIN-999"
    response = await api.post(
        "/api/v1/iot/captures",
        files=upload_files(make_jpeg()),
        data=data,
        headers={"X-Device-Key": DEVICE_KEY},
    )
    assert response.status_code == 401


# ─── Image upload and validation ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_capture_runs_privacy_pipeline(api: AsyncClient, api_session: Session, device_keys, mock_classifier):
    response = await api.post(
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
async def test_capture_rejects_invalid_image(api: AsyncClient, api_session: Session, device_keys, mock_classifier):
    response = await api.post(
        "/api/v1/iot/captures",
        files={"image": ("capture.jpg", b"this is not an image", "image/jpeg")},
        data=upload_data(),
        headers={"X-Device-Key": DEVICE_KEY},
    )
    assert response.status_code == 422
    mock_classifier.assert_not_called()  # garbage never reaches the model


@pytest.mark.asyncio
async def test_capture_rejects_empty_upload(api: AsyncClient, api_session: Session, device_keys, mock_classifier):
    response = await api.post(
        "/api/v1/iot/captures",
        files={"image": ("capture.jpg", b"", "image/jpeg")},
        data=upload_data(),
        headers={"X-Device-Key": DEVICE_KEY},
    )
    assert response.status_code == 422


# ─── Classifier reuse (spec §9 — no separate IoT classifier) ─────────────────


@pytest.mark.asyncio
async def test_iot_capture_goes_through_the_4_tang_classifier(
    api: AsyncClient, api_session: Session, device_keys, mock_classifier
):
    """The IoT path must run the same 4-tier classifier as every image source."""
    response = await api.post(
        "/api/v1/iot/captures",
        files=upload_files(make_jpeg()),
        data=upload_data(),
        headers={"X-Device-Key": DEVICE_KEY},
    )

    assert response.status_code == 200
    assert response.json()["label"] == "recyclable_plastic"
    mock_classifier.assert_called_once()
    # And it received a preprocessed image with a phash, not the raw upload.
    args, kwargs = mock_classifier.call_args
    assert kwargs["image_phash"]
    assert kwargs["image_bytes"]


# ─── Uncertain results (spec §11) ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ca_tu_choi_tra_unknown_va_review(
    api: AsyncClient, api_session: Session, device_keys, monkeypatch
):
    def _tu_choi(session, image_bytes=None, image_phash=""):
        return ClassifyOutcome(category=None, confidence=0.0, refused=True)

    with patch("src.api.iot.classify_waste", side_effect=_tu_choi):
        response = await api.post(
            "/api/v1/iot/captures",
            files=upload_files(make_jpeg()),
            data=upload_data(),
            headers={"X-Device-Key": DEVICE_KEY},
        )
    body = response.json()
    assert body["status"] == "refused"
    assert body["label"] == "UNKNOWN"
    assert body["requires_review"] is True
    assert body["review_required"] is True


@pytest.mark.asyncio
async def test_ca_nguy_hai_luon_review(
    api: AsyncClient, api_session: Session, device_keys, monkeypatch
):
    def _nguy_hai(session, image_bytes=None, image_phash=""):
        nhom = api_session.scalar(select(WasteCategory).where(WasteCategory.code == "hazardous"))
        return ClassifyOutcome(category=nhom, confidence=0.99, refused=False)

    with patch("src.api.iot.classify_waste", side_effect=_nguy_hai):
        response = await api.post(
            "/api/v1/iot/captures",
            files=upload_files(make_jpeg()),
            data=upload_data(),
            headers={"X-Device-Key": DEVICE_KEY},
        )
    body = response.json()
    assert body["status"] == "hazard"
    assert body["label"] == "hazardous"
    assert body["requires_review"] is True
    assert body["review_required"] is True


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


@pytest.mark.asyncio
async def test_get_readings_doc_lai_tu_csdl(
    api: AsyncClient, api_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Gói P61: ghi qua POST rồi GET phải đọc lại đúng — không còn trả rỗng."""
    _dat_khoa_thiet_bi(monkeypatch, KHOI_CHUNG)
    _tao_thung(api_session, code="BIN-GET")
    api_session.commit()

    post = await api.post(
        "/api/v1/bins/BIN-GET/readings",
        json={"device_id": DEVICE_ID, "fill_percent": 63.5, "is_full": False},
        headers={"X-Device-Key": KHOI_CHUNG},
    )
    assert post.status_code == 200, post.text

    response = await api.get("/api/v1/bins/BIN-GET/readings")
    assert response.status_code == 200, response.text
    cac_dong = response.json()
    assert len(cac_dong) == 1, "GET phải đọc lại đúng reading vừa ghi"
    assert cac_dong[0]["fill_percent"] == pytest.approx(63.5)
    assert cac_dong[0]["source"] == "device"
    assert cac_dong[0]["created_at"], "Phải kèm mốc thời gian"


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
