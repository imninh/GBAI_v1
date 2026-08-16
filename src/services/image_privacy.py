"""Image validation and privacy preprocessing.

Every image — from the PWA or from an IoT device — passes through
``preprocess_image`` before it can reach an external Vision provider. There is
deliberately no bypass: :mod:`src.services.classification` accepts a
``ProcessedImage``, not raw bytes, so an unprocessed image cannot physically be
handed to a model provider.

Pipeline order matters (spec §10):

1. validate the image is real and within limits
2. strip EXIF metadata (GPS coordinates and timestamps live here)
3. blur detected faces
4. resize / compress
5. compute a perceptual hash

Face detection uses OpenCV's bundled Haar cascade. If OpenCV is unavailable the
step does not silently vanish: ``faces_blurred`` becomes ``None`` and a warning
is logged, so the caller can tell "no faces found" from "not checked".
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

from PIL import Image

logger = logging.getLogger(__name__)

try:  # pragma: no cover - exercised by whichever branch the environment takes
    import cv2
    import numpy as np

    _FACE_CASCADE = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    _FACE_DETECTION_AVAILABLE = not _FACE_CASCADE.empty()
except Exception:  # noqa: BLE001 - any import/env failure degrades the same way
    _FACE_DETECTION_AVAILABLE = False
    logger.warning("OpenCV unavailable; face blurring is DISABLED")

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MIN_DIMENSION = 32
MAX_DIMENSION = 8000
TARGET_MAX_EDGE = 1024
JPEG_QUALITY = 85
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


class ImageValidationError(ValueError):
    """Raised when an upload is not a usable image."""


@dataclass(frozen=True)
class ProcessedImage:
    """An image that has completed the privacy pipeline.

    Holding one of these is the proof that preprocessing ran; the classification
    service will not accept anything else.
    """

    content: bytes
    width: int
    height: int
    phash: str
    original_format: str
    faces_blurred: int | None
    exif_stripped: bool

    @property
    def size_bytes(self) -> int:
        return len(self.content)


def _validate(raw: bytes) -> Image.Image:
    if not raw:
        raise ImageValidationError("Empty upload")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ImageValidationError(
            f"Image exceeds {MAX_UPLOAD_BYTES} bytes (got {len(raw)})"
        )

    try:
        probe = Image.open(io.BytesIO(raw))
        probe.verify()  # structural check; consumes the object
    except Exception as exc:  # noqa: BLE001 - Pillow raises many types here
        raise ImageValidationError(f"Not a decodable image: {exc}") from exc

    image = Image.open(io.BytesIO(raw))  # reopen: verify() left it unusable
    if image.format not in ALLOWED_FORMATS:
        raise ImageValidationError(f"Unsupported format: {image.format}")
    if image.width < MIN_DIMENSION or image.height < MIN_DIMENSION:
        raise ImageValidationError(
            f"Image too small: {image.width}x{image.height}"
        )
    if image.width > MAX_DIMENSION or image.height > MAX_DIMENSION:
        raise ImageValidationError(
            f"Image too large: {image.width}x{image.height}"
        )
    return image


def _strip_exif(image: Image.Image) -> Image.Image:
    """Drop every metadata block by copying pixels into a fresh image.

    Re-saving with ``exif=b""`` is not enough — Pillow carries other metadata
    containers (XMP, ICC, PNG text chunks) across a save. Rebuilding from raw
    pixel data leaves nothing behind.
    """
    converted = image.convert("RGB")
    return Image.frombytes("RGB", converted.size, converted.tobytes())


def _blur_faces(image: Image.Image) -> tuple[Image.Image, int | None]:
    if not _FACE_DETECTION_AVAILABLE:
        # Explicitly unknown, not zero. The caller must be able to tell the
        # difference between "checked, none found" and "never checked".
        return image, None

    frame = np.array(image)
    gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    faces = _FACE_CASCADE.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)

    for x, y, w, h in faces:
        region = frame[y : y + h, x : x + w]
        # Kernel scaled to the face so the blur is irreversible at any face size.
        kernel = max(3, (w // 3) | 1)
        frame[y : y + h, x : x + w] = cv2.GaussianBlur(region, (kernel, kernel), 0)

    return Image.fromarray(frame), len(faces)


def _resize(image: Image.Image) -> Image.Image:
    longest = max(image.width, image.height)
    if longest <= TARGET_MAX_EDGE:
        return image
    scale = TARGET_MAX_EDGE / longest
    new_size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
    return image.resize(new_size, Image.Resampling.LANCZOS)


def compute_phash(image: Image.Image, hash_size: int = 8) -> str:
    """Perceptual hash (average-hash) as a hex string.

    Used for deduplicating near-identical captures — a bin camera photographing
    the same static pile repeatedly should not be billed as a new inference.
    Implemented directly to avoid another dependency.
    """
    small = image.convert("L").resize(
        (hash_size, hash_size), Image.Resampling.LANCZOS
    )
    # "L" mode is one byte per pixel, so tobytes() is already the pixel list.
    pixels = list(small.tobytes())
    average = sum(pixels) / len(pixels)
    bits = "".join("1" if pixel >= average else "0" for pixel in pixels)
    return f"{int(bits, 2):0{hash_size * hash_size // 4}x}"


def preprocess_image(raw: bytes) -> ProcessedImage:
    """Run the full privacy pipeline. Raises ImageValidationError on bad input."""
    image = _validate(raw)
    original_format = image.format or "UNKNOWN"

    stripped = _strip_exif(image)
    deidentified, faces_blurred = _blur_faces(stripped)
    resized = _resize(deidentified)
    phash = compute_phash(resized)

    buffer = io.BytesIO()
    resized.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)

    return ProcessedImage(
        content=buffer.getvalue(),
        width=resized.width,
        height=resized.height,
        phash=phash,
        original_format=original_format,
        faces_blurred=faces_blurred,
        exif_stripped=True,
    )
