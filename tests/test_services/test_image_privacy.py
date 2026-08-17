"""Tests for the image privacy pipeline (spec §10)."""

import io
import re
from pathlib import Path

import pytest
from PIL import Image

from src.services.image_privacy import (
    MAX_UPLOAD_BYTES,
    TARGET_MAX_EDGE,
    ImageValidationError,
    compute_phash,
    preprocess_image,
)


def make_jpeg(width=800, height=600, colour=(120, 200, 90), with_exif=True) -> bytes:
    image = Image.new("RGB", (width, height), colour)
    buffer = io.BytesIO()
    if with_exif:
        exif = image.getexif()
        exif[271] = "TestCameraMake"
        exif[272] = "TestCameraModel"
        exif[306] = "2026:08:11 10:30:00"  # DateTime
        image.save(buffer, format="JPEG", exif=exif)
    else:
        image.save(buffer, format="JPEG")
    return buffer.getvalue()


def test_exif_is_stripped():
    raw = make_jpeg(with_exif=True)
    # Sanity: the fixture really does carry EXIF before processing.
    assert dict(Image.open(io.BytesIO(raw)).getexif())

    processed = preprocess_image(raw)

    assert processed.exif_stripped is True
    assert not dict(Image.open(io.BytesIO(processed.content)).getexif())


def test_large_image_is_resized():
    processed = preprocess_image(make_jpeg(3000, 2000))
    assert max(processed.width, processed.height) == TARGET_MAX_EDGE
    assert processed.width == TARGET_MAX_EDGE  # landscape stays landscape


def test_small_image_is_not_upscaled():
    processed = preprocess_image(make_jpeg(320, 240))
    assert (processed.width, processed.height) == (320, 240)


def test_output_is_always_jpeg():
    image = Image.new("RGB", (400, 400), (10, 20, 30))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    processed = preprocess_image(buffer.getvalue())

    assert processed.original_format == "PNG"
    assert Image.open(io.BytesIO(processed.content)).format == "JPEG"


def test_phash_is_stable_and_discriminating():
    red = Image.new("RGB", (200, 200), (255, 0, 0))
    gradient = Image.linear_gradient("L").convert("RGB")

    assert compute_phash(red) == compute_phash(red.copy())
    assert compute_phash(red) != compute_phash(gradient)


def test_phash_is_present_on_processed_image():
    processed = preprocess_image(make_jpeg())
    assert processed.phash
    assert len(processed.phash) == 16  # 8x8 bits as hex


def test_faces_blurred_is_int_or_none_never_silently_zero():
    """None means "not checked"; an int means detection actually ran."""
    processed = preprocess_image(make_jpeg())
    assert processed.faces_blurred is None or isinstance(processed.faces_blurred, int)


@pytest.mark.parametrize(
    "payload",
    [b"", b"not an image at all", b"\xff\xd8\xff\xe0truncated"],
)
def test_invalid_payloads_are_rejected(payload):
    with pytest.raises(ImageValidationError):
        preprocess_image(payload)


def test_oversized_payload_is_rejected():
    with pytest.raises(ImageValidationError, match="exceeds"):
        preprocess_image(b"\xff\xd8" + b"\x00" * MAX_UPLOAD_BYTES)


def test_tiny_image_is_rejected():
    with pytest.raises(ImageValidationError, match="too small"):
        preprocess_image(make_jpeg(8, 8, with_exif=False))


def test_wokwi_mock_camera_fixture_passes_the_privacy_pipeline():
    """Keep the firmware's embedded simulation image honest.

    Marker-only JPEG bytes can look plausible in C while still being rejected by
    Pillow. Parse the exact array compiled into the Wokwi firmware and send it
    through the same preprocessing entry point as a real upload.
    """
    repo_root = Path(__file__).parents[2]
    header = (repo_root / "iot/firmware/include/hw/mock_camera.h").read_text()
    initializer = header.split("kFixtureJpeg[] = {", 1)[1].split("};", 1)[0]
    raw = bytes(int(value, 16) for value in re.findall(r"0x([0-9A-Fa-f]{2})", initializer))

    processed = preprocess_image(raw)

    assert (processed.width, processed.height) == (160, 120)
    assert processed.size_bytes > 0
