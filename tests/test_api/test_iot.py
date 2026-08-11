"""Tests for the IoT device API: auth, upload, privacy pipeline, bin readings."""

import io
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image

from src.config import get_settings
from src.models.schemas import ClassifyOutcome
from src.services import bin_readings, device_auth

DEVICE_ID = "GBIN-001"
DEVICE_KEY = "test-key-123"


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
def clean_readings():
    bin_readings.get_repository().clear()
    yield
    bin_readings.get_repository().clear()


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


@pytest.mark.asyncio
async def test_bin_reading_accepted(client, device_keys):
    response = await client.post(
        "/api/v1/bins/BIN-001/readings",
        json={"device_id": DEVICE_ID, "fill_percent": 84.5, "is_full": True, "uptime_s": 900},
        headers={"X-Device-Key": DEVICE_KEY},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["bin_code"] == "BIN-001"
    assert body["fill_percent"] == pytest.approx(84.5)
    assert body["is_full"] is True
    assert body["reading_id"]


@pytest.mark.asyncio
async def test_bin_reading_requires_device_key(client, device_keys):
    response = await client.post(
        "/api/v1/bins/BIN-001/readings",
        json={"device_id": DEVICE_ID, "fill_percent": 50.0, "is_full": False},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("fill_percent", [-1.0, 100.1, 1000.0])
async def test_bin_reading_rejects_out_of_range_fill(client, device_keys, fill_percent):
    """A device must not be able to store an impossible fill level (spec §13)."""
    response = await client.post(
        "/api/v1/bins/BIN-001/readings",
        json={"device_id": DEVICE_ID, "fill_percent": fill_percent, "is_full": False},
        headers={"X-Device-Key": DEVICE_KEY},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_bin_readings_are_listed_in_order(client, device_keys):
    for percent in (20.0, 55.0, 88.0):
        await client.post(
            "/api/v1/bins/BIN-001/readings",
            json={
                "device_id": DEVICE_ID,
                "fill_percent": percent,
                "is_full": percent >= 80,
            },
            headers={"X-Device-Key": DEVICE_KEY},
        )

    response = await client.get("/api/v1/bins/BIN-001/readings")
    assert response.status_code == 200
    readings = response.json()
    assert [r["fill_percent"] for r in readings] == [20.0, 55.0, 88.0]
    assert readings[-1]["is_full"] is True
