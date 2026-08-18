"""IoT device API — image captures and bin fill readings.

Thin by design (spec §9): this module handles HTTP concerns only — auth,
parsing, status codes. Every decision lives in ``src/services``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile

from src.models.schemas import (
    HeartbeatRequest,
    HeartbeatResponse,
    IoTCaptureResponse,
)
from src.services import bin_readings
from src.services.classification import classify_processed_image
from src.services.device_auth import DeviceAuthError, authenticate
from src.services.image_privacy import ImageValidationError, preprocess_image

router = APIRouter()


async def require_device_key(x_device_key: str | None = Header(default=None)) -> str:
    """FastAPI dependency: authenticate the caller as a known device."""
    try:
        return authenticate(x_device_key)
    except DeviceAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/iot/captures", response_model=IoTCaptureResponse)
async def create_capture(
    image: UploadFile = File(...),
    device_id: str = Form(...),
    bin_code: str = Form(...),
    event_type: str = Form(default="waste_detected"),
    uptime_s: int = Form(default=0),
    fill_percent: float | None = Form(default=None),
    authenticated_device: str = Depends(require_device_key),
) -> IoTCaptureResponse:
    """Accept a JPEG from a device, preprocess it, classify it, return the result."""
    # A valid key for device A may not post as device B.
    if device_id != authenticated_device:
        raise HTTPException(status_code=401, detail="Invalid device credentials")

    raw = await image.read()

    try:
        processed = preprocess_image(raw)
    except ImageValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Only ever a ProcessedImage reaches the classifier — the privacy pipeline
    # cannot be skipped from here (spec §10).
    outcome = await classify_processed_image(processed, source="iot")

    # A capture may carry a fill reading; recording it is best-effort and must
    # never fail the classification response.
    if fill_percent is not None and 0.0 <= fill_percent <= 100.0:
        try:
            bin_readings.record_reading(
                bin_code=bin_code,
                device_id=device_id,
                fill_percent=fill_percent,
                is_full=False,
                uptime_s=uptime_s,
            )
        except ValueError:
            pass

    return IoTCaptureResponse(
        status=outcome.status,
        label=outcome.label,
        confidence=outcome.confidence,
        requires_review=outcome.requires_review,
        message=outcome.message,
        capture_id=str(uuid.uuid4()),
        phash=processed.phash,
        image_bytes=processed.size_bytes,
        faces_blurred=processed.faces_blurred,
        exif_stripped=processed.exif_stripped,
    )


@router.post("/iot/heartbeat", response_model=HeartbeatResponse)
async def heartbeat(
    payload: HeartbeatRequest,
    authenticated_device: str = Depends(require_device_key),
) -> HeartbeatResponse:
    """Confirm to a device that the backend is reachable (IoT Checkpoint 1 §21).

    Stateless on purpose: it stores nothing. Its only job is to let a bin
    distinguish "my Wi-Fi is up" from "the backend is actually answering", which
    is the difference the device cannot work out on its own.
    """
    if payload.device_id != authenticated_device:
        raise HTTPException(status_code=401, detail="Invalid device credentials")

    return HeartbeatResponse(
        status="ok",
        device_id=authenticated_device,
        server_time=datetime.now(UTC),
    )
