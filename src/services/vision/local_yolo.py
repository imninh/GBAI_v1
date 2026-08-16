"""Tầng T0.5b — YOLO11n phát hiện đồ điện tử tại chỗ, không gọi API (gói P33).

Đo trên ảnh rác thật ngày 03/08: model đám mây ở T1 nhận ra đồ điện tử 0–1/6
(``llama-3.2-90b`` 0/6, ``nemotron-12b`` 1/6) trong khi YOLO11n chạy tại chỗ
4/4 trong ~100 ms và $0. Đồ điện tử lẫn trong ảnh rác bị gán thành rác thường —
chỉ số an toàn "nguy hại thành rác thường" đang trượt vì chỗ mù đó.

YOLO ở đây **không phải một tầng phân loại rác**, nó là một **cảm biến cảnh
báo**:

* YOLO11n biết **80 lớp COCO, không biết rác** — không lớp nào cho "vỏ hộp sữa",
  "túi nilon", "hộp xốp". Đừng ai cắm nó vào đường chốt nhãn.
* Model local **không bao giờ tự chốt nhóm nguy hại** (``local_never_decides_
  hazardous``) — YOLO chỉ giơ cờ, và cờ đó ép hệ thống hỏi model mạnh hơn.

Rơi êm tuyệt đối: thiếu ``onnxruntime`` / thiếu file model / ảnh hỏng / model
ném lỗi — tất cả đều trả về "không nghi" và ghi ``logger.warning``, không ngoại
lệ nào thoát ra ngoài.
"""

from __future__ import annotations

import io
import logging
import threading
from pathlib import Path
from typing import Any

from PIL import Image

from src.config import get_settings

logger = logging.getLogger(__name__)

# Sáu lớp COCO này gộp lại thành MỘT tín hiệu duy nhất: "có đồ điện tử trong
# ảnh". Đây là toàn bộ giá trị của YOLO trong sản phẩm này — đúng chỗ T1 mù.
DO_DIEN_TU = frozenset({"cell phone", "laptop", "tv", "keyboard", "mouse", "remote"})

# Ánh xạ lớp COCO → mã nhóm rác. CHỈ ghi những lớp có MỘT nghĩa duy nhất.
#
# "bottle" KHÔNG có trong bảng: một hộp COCO gắn nhãn `bottle` chỉ nói hình dạng
# cái chai, không nói chất liệu — danh mục có CẢ `recyclable_plastic` lẫn
# `recyclable_glass`, gắn thẳng sang nhựa là bịa ra thông tin dữ liệu không có,
# và sai với mọi chai thuỷ tinh, im lặng. "cup" cũng vậy (cốc giấy/cốc nhựa/cốc
# thuỷ tinh). Lớp mơ hồ để CLIP hoặc T1 phân xử — chúng nhìn được chất liệu.
MAP_COCO_RAC = {
    "book": "recyclable_paper",
}

# 80 lớp COCO theo đúng thứ tự chỉ số của YOLO11n (ultralytics export).
COCO_NAMES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat", "traffic light",
    "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove", "skateboard", "surfboard",
    "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard", "cell phone",
    "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
    "hair drier", "toothbrush",
]

YOLO_MODEL_FILE = "yolo11n.onnx"

_session: Any = None
_failed = False

# Tải file model chỉ được chạy một lần dù nhiều luồng cùng gọi.
_tai_lock = threading.Lock()


def _giai_url_trang_release(url: str) -> str:
    """Đổi link **trang** Release của GitHub thành link **file** .onnx.

    Dán nhầm link trang là chuyện rất dễ xảy ra — nút copy trên GitHub cho ra
    ``…/releases/tag/<tag>`` chứ không phải ``…/releases/download/<tag>/<file>``.
    Tải link trang về thì được một trang HTML, lưu thành file .onnx hỏng, và tầng
    YOLO tắt mà không ai hiểu vì sao.

    Trả về URL gốc nếu không phải link trang release hoặc không tra được.
    """
    if "/releases/tag/" not in url:
        return url

    import httpx

    repo, _, tag = url.partition("/releases/tag/")
    repo = repo.replace("https://github.com/", "", 1).strip("/")
    api = f"https://api.github.com/repos/{repo}/releases/tags/{tag.strip('/')}"
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            assets = client.get(api).raise_for_status().json().get("assets", [])
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("YOLO_ASSETS_URL là link trang Release mà không tra được file đính kèm: %s", exc)
        return url

    for asset in assets:
        if str(asset.get("name", "")).endswith(".onnx"):
            duong_dan = str(asset["browser_download_url"])
            logger.info("YOLO_ASSETS_URL trỏ vào trang Release — dùng file đính kèm %s", asset["name"])
            return duong_dan
    logger.warning("Release '%s' không có file .onnx nào đính kèm.", tag)
    return url


def _tai_asset_neu_thieu(thu_muc: Path) -> None:
    """Tải file model YOLO từ ``yolo_assets_url`` nếu máy chưa có.

    Máy chủ miễn phí dùng đĩa tạm nên file mất sau mỗi lần khởi động lại — tải
    lại mỗi lần bật là chấp nhận được vì việc này chạy ở luồng nền.
    """
    url = get_settings().yolo_assets_url
    if not url or (thu_muc / YOLO_MODEL_FILE).exists():
        return

    import httpx

    url = _giai_url_trang_release(url)
    thu_muc.mkdir(parents=True, exist_ok=True)
    logger.info("Tải model YOLO từ %s …", url)
    try:
        with httpx.Client(timeout=300.0, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
        # YOLO11n ONNX bắt đầu bằng magic bytes ONNX; dữ liệu nhỏ hơn ~1 MB thì
        # gần như chắc chắn là một trang web chứ không phải model.
        if len(response.content) < 1_000_000:
            logger.warning(
                "YOLO_ASSETS_URL trả về %d byte (có vẻ là trang web, không phải model .onnx ~10 MB). "
                "Tầng YOLO tạm tắt.",
                len(response.content),
            )
            return
        (thu_muc / YOLO_MODEL_FILE).write_bytes(response.content)
    except (httpx.HTTPError, OSError) as exc:
        logger.warning("Không tải được model YOLO: %s. Bỏ qua tầng này.", exc)


def _load() -> Any | None:
    """Nạp phiên ONNX của YOLO11n. ``None`` nếu không dùng được."""
    global _session, _failed
    if _failed:
        return None
    if _session is not None:
        return _session

    with _tai_lock:
        if _session is not None:
            return _session

        thu_muc = Path(get_settings().yolo_onnx_dir)
        _tai_asset_neu_thieu(thu_muc)

        model_path = thu_muc / YOLO_MODEL_FILE
        if not model_path.exists():
            logger.info("Chưa có model YOLO ở %s — bỏ qua tầng.", thu_muc)
            _failed = True
            return None

        try:
            import onnxruntime as ort
        except ImportError:
            logger.warning("Chưa cài onnxruntime — bỏ qua tầng YOLO (cài theo requirements-local-model.txt).")
            _failed = True
            return None

        try:
            session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
        except (OSError, ValueError) as exc:
            logger.warning("Model YOLO hỏng: %s. Bỏ qua.", exc)
            _failed = True
            return None

        _session = session
        logger.info("Đã nạp YOLO11n: %s", model_path)
        return session


def is_loaded() -> bool:
    """True nếu phiên YOLO đã nạp sẵn — CHỈ ĐỌC, không kích hoạt tải.

    Khác ``_load()``: hàm này chỉ đọc biến module ``_session``, không bao giờ tải model
    hay dựng InferenceSession. Dùng cho ``/ops/metrics`` (endpoint chỉ đọc).
    """
    return _session is not None


def _tien_xu_ly_anh(image: Image.Image, size: int = 640):
    """Đưa ảnh về tensor (1, 3, 640, 640) theo kiểu letterbox của YOLO."""
    import numpy as np

    rong, cao = image.size
    ti_le = size / max(rong, cao)
    image = image.resize((round(rong * ti_le), round(cao * ti_le)), Image.BILINEAR)
    to = Image.new("RGB", (size, size), (114, 114, 114))
    to.paste(image, ((size - image.width) // 2, (size - image.height) // 2))
    arr = np.asarray(to, dtype=np.float32) / 255.0
    return arr.transpose(2, 0, 1)[None].astype(np.float32)


def _iou(a: list[float], b: list[float]) -> float:
    """Intersection-over-Union của hai hộp ``[x1, y1, x2, y2]``."""
    x1, y1, x2, y2 = a
    x3, y3, x4, y4 = b
    giao_x1, giao_y1 = max(x1, x3), max(y1, y3)
    giao_x2, giao_y2 = min(x2, x4), min(y2, y4)
    giao = max(0.0, giao_x2 - giao_x1) * max(0.0, giao_y2 - giao_y1)
    dien_tich_a = (x2 - x1) * (y2 - y1)
    dien_tich_b = (x4 - x3) * (y4 - y3)
    hop = dien_tich_a + dien_tich_b - giao
    return giao / hop if hop > 0 else 0.0


def _loc_ket_qua(dau_ra, nguong: float) -> list[dict]:
    """Output thô của YOLO → danh sách phát hiện, đã lọc ngưỡng và NMS đơn giản.

    Output dạng ``[1, 84, 8400]`` hoặc ``[1, 8400, 84]``; 84 = 4 toạ độ hộp +
    80 điểm lớp COCO. Trả ``[{"lop": ..., "diem": ...}]`` sắp giảm theo điểm.
    """
    import numpy as np

    mang = np.asarray(dau_ra, dtype=np.float32)
    if mang.ndim == 3:
        mang = mang[0].transpose(1, 0)
    cac_vat: list[dict] = []
    for dong in mang:
        diem_lop = dong[4:]
        chi_so = int(np.argmax(diem_lop))
        diem = float(diem_lop[chi_so])
        if diem < nguong:
            continue
        cx, cy, w, h = [float(v) for v in dong[:4]]
        cac_vat.append(
            {
                "lop": COCO_NAMES[chi_so],
                "diem": round(diem, 3),
                "box": [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2],
            }
        )

    cac_vat.sort(key=lambda v: v["diem"], reverse=True)
    giu: list[dict] = []
    for vat in cac_vat:
        if all(_iou(vat["box"], g["box"]) < 0.45 for g in giu):
            giu.append(vat)
    return [{"lop": g["lop"], "diem": g["diem"]} for g in giu]


def phat_hien(image_bytes: bytes) -> list[dict] | None:
    """Chạy YOLO11n trên ảnh, trả danh sách vật thể phát hiện được.

    Returns:
        ``[{"lop": "cell phone", "diem": 0.87}, …]`` đã lọc theo
        ``yolo_confidence``, sắp giảm dần theo điểm. ``None`` khi tắt cờ / chưa
        nạp được model / ảnh hỏng — **không bao giờ ném ngoại lệ ra ngoài**.
    """
    settings = get_settings()
    if not settings.yolo_enabled:
        return None
    model = _load()
    if model is None:
        return None

    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except (OSError, ValueError):
        return None

    try:
        pixel_values = _tien_xu_ly_anh(image)
        output = model.run(None, {"images": pixel_values})[0]
    except Exception as exc:
        logger.warning("Chạy YOLO lỗi: %s. Bỏ qua tầng.", exc)
        return None
    return _loc_ket_qua(output, settings.yolo_confidence)


def nghi_do_dien_tu(image_bytes: bytes) -> tuple[bool, list[dict]]:
    """Ảnh này có đồ điện tử không?

    Returns:
        ``(nghi, cac_vat)``. ``nghi=True`` khi có ít nhất một vật thuộc
        ``DO_DIEN_TU`` **và** điểm đạt ``yolo_confidence``. Tắt cờ / hỏng →
        ``(False, [])`` — im lặng, không cản trở.
    """
    try:
        cac_vat = phat_hien(image_bytes) or []
    except Exception as exc:
        logger.warning("YOLO lỗi không ngờ: %s. Bỏ qua tầng.", exc)
        return False, []

    nguong = get_settings().yolo_confidence
    du_nguong = [v for v in cac_vat if float(v.get("diem", 0.0)) >= nguong]
    nghi = any(v.get("lop") in DO_DIEN_TU for v in du_nguong)
    return nghi, du_nguong
