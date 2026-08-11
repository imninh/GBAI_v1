"""Tiền xử lý ảnh cư dân — hàng rào quyền riêng tư của hệ thống.

Ảnh chụp thùng rác nhạy cảm hơn người ta tưởng: nó có thể chứa khuôn mặt, số
căn hộ, hoá đơn có tên và địa chỉ, nhãn thuốc. Và **mọi ảnh điện thoại đều
mang EXIF chứa toạ độ GPS chính xác tới mét**.

Vì vậy không ảnh nào được rời khỏi máy chủ đi tới API model khi chưa qua
:func:`preprocess_image`:

1. tước toàn bộ EXIF (ghi lại các trường đã xoá để trả về cho màn 4.5)
2. làm mờ khuôn mặt (Haar cascade — đủ dùng, chạy CPU, không cần model ngoài)
3. nén cạnh dài về 512px
4. tính pHash làm khoá cache tầng T0

Kết quả trả về đủ để dựng bảng đối chiếu "ảnh gốc / đã gửi đi" trên UI —
biến một việc backend vô hình thành bằng chứng tuân thủ nhìn thấy được.
"""

from __future__ import annotations

import io
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import cv2
import imagehash
import numpy as np
from PIL import Image, ImageFilter
from PIL.ExifTags import GPSTAGS, TAGS

from src.config import get_settings

# Các trường EXIF được nêu đích danh trên UI. Trường nào khác vẫn bị xoá sạch,
# chỉ là không cần liệt kê từng cái cho người dùng đọc.
_INTERESTING_EXIF_TAGS = {
    "GPSInfo": "Toạ độ GPS",
    "DateTime": "Thời gian chụp",
    "DateTimeOriginal": "Thời gian chụp",
    "Make": "Hãng điện thoại",
    "Model": "Model điện thoại",
    "Software": "Phần mềm chỉnh sửa",
    "Artist": "Tác giả",
    "GPSLatitude": "Vĩ độ",
    "GPSLongitude": "Kinh độ",
}

_FACE_CASCADE_FILE = "haarcascade_frontalface_default.xml"
_face_cascade: cv2.CascadeClassifier | None = None


@dataclass
class RemovedField:
    """Một trường metadata đã bị xoá, kèm giá trị trước khi xoá.

    Giá trị trước khi xoá chỉ hiện cho chính chủ ảnh (spec 4.5) — nó là bằng
    chứng "hệ thống đã xoá thật", không phải dữ liệu đem đi dùng việc khác.
    """

    field_name: str
    label_vi: str
    value_before: str


@dataclass
class ProcessedImage:
    """Kết quả tiền xử lý — map thẳng vào bảng ``media``."""

    stored_path: str
    original_path: str
    phash: str
    width: int
    height: int
    bytes_size: int
    original_width: int
    original_height: int
    original_bytes_size: int
    exif_stripped: bool
    faces_blurred: int
    removed_fields: list[RemovedField] = field(default_factory=list)
    expires_at: datetime | None = None

    def removed_fields_as_json(self) -> list[dict[str, str]]:
        return [
            {"field": r.field_name, "label_vi": r.label_vi, "value_before": r.value_before}
            for r in self.removed_fields
        ]


def _get_face_cascade() -> cv2.CascadeClassifier | None:
    """Nạp Haar cascade một lần rồi dùng lại.

    Trả về ``None`` nếu OpenCV không kèm sẵn file cascade — khi đó bỏ qua bước
    làm mờ mặt và ghi ``faces_blurred=0`` thay vì làm hỏng cả pipeline.
    """
    global _face_cascade
    if _face_cascade is not None:
        return _face_cascade

    cascade_path = Path(cv2.data.haarcascades) / _FACE_CASCADE_FILE
    if not cascade_path.exists():
        return None

    cascade = cv2.CascadeClassifier(str(cascade_path))
    if cascade.empty():
        return None

    _face_cascade = cascade
    return _face_cascade


def _format_gps(gps_info: dict) -> str:
    """Đổi khối GPSInfo của EXIF thành chuỗi ``10.776900, 106.700900``."""

    def to_degrees(values: object) -> float | None:
        try:
            d, m, s = (float(v) for v in values)  # type: ignore[misc]
        except (TypeError, ValueError):
            return None
        return d + m / 60 + s / 3600

    named = {GPSTAGS.get(k, str(k)): v for k, v in gps_info.items()}
    lat = to_degrees(named.get("GPSLatitude"))
    lng = to_degrees(named.get("GPSLongitude"))
    if lat is None or lng is None:
        return "có dữ liệu vị trí"

    if str(named.get("GPSLatitudeRef", "N")).upper() == "S":
        lat = -lat
    if str(named.get("GPSLongitudeRef", "E")).upper() == "W":
        lng = -lng
    return f"{lat:.6f}, {lng:.6f}"


def extract_removed_fields(image: Image.Image) -> list[RemovedField]:
    """Liệt kê các trường EXIF sẽ bị xoá, kèm giá trị hiện tại."""
    try:
        exif = image.getexif()
    except (OSError, AttributeError):
        return []
    if not exif:
        return []

    removed: list[RemovedField] = []
    for tag_id, value in exif.items():
        name = TAGS.get(tag_id, str(tag_id))
        if name not in _INTERESTING_EXIF_TAGS:
            continue
        if name == "GPSInfo":
            try:
                gps = exif.get_ifd(tag_id)
            except (OSError, ValueError, KeyError):
                gps = {}
            text = _format_gps(gps) if gps else "có dữ liệu vị trí"
        else:
            text = str(value).strip()
        if not text:
            continue
        removed.append(RemovedField(field_name=name, label_vi=_INTERESTING_EXIF_TAGS[name], value_before=text))
    return removed


def blur_faces(image: Image.Image) -> tuple[Image.Image, int]:
    """Làm mờ mọi khuôn mặt tìm được. Trả về ảnh mới và số mặt đã xử lý."""
    cascade = _get_face_cascade()
    if cascade is None:
        return image, 0

    rgb = np.array(image.convert("RGB"))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(28, 28))
    if len(faces) == 0:
        return image, 0

    result = image.convert("RGB")
    for x, y, w, h in faces:
        box = (int(x), int(y), int(x + w), int(y + h))
        # Bán kính theo kích thước mặt để mặt nhỏ cũng mờ hẳn, không chỉ nhoè nhẹ.
        radius = max(8, int(max(w, h) / 4))
        patch = result.crop(box).filter(ImageFilter.GaussianBlur(radius=radius))
        result.paste(patch, box)
    return result, len(faces)


def _resize_to_max_edge(image: Image.Image, max_edge: int) -> Image.Image:
    if max(image.size) <= max_edge:
        return image
    ratio = max_edge / max(image.size)
    new_size = (max(1, round(image.width * ratio)), max(1, round(image.height * ratio)))
    return image.resize(new_size, Image.LANCZOS)


def _strip_exif(image: Image.Image) -> Image.Image:
    """Tạo ảnh mới chỉ gồm pixel — mọi metadata bị bỏ lại phía sau.

    Cách chắc chắn nhất: dựng ``Image`` mới từ dữ liệu điểm ảnh. Không dùng
    ``del image.info[...]`` vì một số trường vẫn sống sót qua bước lưu file.
    """
    clean = Image.new(image.mode, image.size)
    clean.putdata(list(image.getdata()))
    return clean


def preprocess_image(
    raw: bytes,
    *,
    media_dir: str | None = None,
    keep_original: bool = True,
) -> ProcessedImage:
    """Chạy trọn 4 bước tiền xử lý trên ảnh thô.

    Args:
        raw: nội dung file ảnh người dùng tải lên.
        media_dir: thư mục lưu ảnh; mặc định lấy từ cấu hình.
        keep_original: có giữ ảnh gốc không. Ảnh gốc chỉ BQL mở được và mỗi
            lần mở đều ghi ``AuditLog``; hết hạn lưu trữ thì xoá cùng ảnh đã xử lý.

    Raises:
        ValueError: khi dữ liệu không phải ảnh đọc được.
    """
    settings = get_settings()
    root = Path(media_dir or settings.media_dir)
    root.mkdir(parents=True, exist_ok=True)

    try:
        source = Image.open(io.BytesIO(raw))
        source.load()
    except (OSError, ValueError) as exc:
        raise ValueError("Không đọc được file ảnh") from exc

    original_width, original_height = source.size
    removed = extract_removed_fields(source)

    stem = f"{datetime.now(UTC):%Y%m%d}-{uuid.uuid4().hex[:12]}"
    original_path = ""
    if keep_original:
        original_file = root / f"{stem}-original.jpg"
        source.convert("RGB").save(original_file, format="JPEG", quality=92)
        original_path = str(original_file)

    working = source.convert("RGB")
    working, faces = (blur_faces(working) if settings.face_blur_enabled else (working, 0))
    working = _resize_to_max_edge(working, settings.media_max_edge_px)
    working = _strip_exif(working)

    stored_file = root / f"{stem}.jpg"
    working.save(stored_file, format="JPEG", quality=85, optimize=True)

    return ProcessedImage(
        stored_path=str(stored_file),
        original_path=original_path,
        phash=str(imagehash.phash(working)),
        width=working.width,
        height=working.height,
        bytes_size=stored_file.stat().st_size,
        original_width=original_width,
        original_height=original_height,
        original_bytes_size=len(raw),
        exif_stripped=True,
        faces_blurred=faces,
        removed_fields=removed,
        expires_at=datetime.now(UTC) + timedelta(days=settings.media_retention_days),
    )


def phash_distance(left: str, right: str) -> int:
    """Khoảng cách Hamming giữa hai chuỗi pHash. Trả về 64 nếu không so được."""
    if not left or not right or len(left) != len(right):
        return 64
    try:
        return imagehash.hex_to_hash(left) - imagehash.hex_to_hash(right)
    except ValueError:
        return 64


def has_exif(path: str | Path) -> bool:
    """Kiểm tra một file ảnh còn EXIF không. Dùng cho test khẳng định."""
    with Image.open(path) as img:
        exif = img.getexif()
        return bool(exif)
