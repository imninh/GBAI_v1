"""Hướng A — ảnh nhiều vật: cắt từng crop rồi CLIP chấm từng cái.

Ca thật (trace #301): một ảnh có 7 chai + bàn phím + cốc. CLIP chấm CẢ khung hình
nên điểm rơi xuống 0,1356 — dưới ngưỡng → không chốt được → leo cloud → hỏng/từ
chối. Với Groq free tier chỉ 8.000 token/phút (đo 16/08) thì gọi cloud cho TỪNG
vật là bất khả thi.

Cách này cắt riêng từng vật (hộp từ :func:`local_yolo.phat_hien_co_hop`, đã quy
về toạ độ ảnh gốc), nới hộp ~8% cho đỡ cụt mép, rồi cho CLIP chấm từng crop. Crop
chỉ có một vật nên điểm cao hẳn → nhiều vật chốt được tại chỗ, $0, không đụng
cloud.

Ràng buộc an toàn — KHÔNG được nới (xem CLAUDE.md mục 5):

* **Không dùng lớp YOLO làm nhãn rác.** ``bottle``/``cup`` mơ hồ chất liệu (nhựa/
  thuỷ tinh/giấy) — YOLO chỉ cho toạ độ, CLIP là người phân xử chất liệu.
* Crop nào CLIP báo ``suspect_hazardous``, hoặc nhóm trả về ``is_hazardous``,
  hoặc YOLO thấy đồ điện tử → trả ``None`` cho CẢ ảnh để rơi về đường cũ
  (cloud + HITL). Giữ nguyên ``local_never_decides_hazardous``.

Hàm này THUẦN: không đụng CSDL, không gọi mạng. Danh mục và hàm CLIP truyền vào
qua tham số để test chèn giả lập.
"""

from __future__ import annotations

import io

from PIL import Image

from src.config import get_settings
from src.services.vision import local_yolo

# Nới hộp thêm ~8% mỗi chiều trước khi cắt: YOLO đóng khung sát vật, cắt thẳng vào
# box dễ cụt mép khiến CLIP nhìn thiếu nửa vật.
_NOI_HOP_TI_LE = 0.08


def _gop_trung_lop(cac_hop: list[dict]) -> list[dict]:
    """Nhiều hộp cùng lớp COCO (7 chai) → một đại diện điểm cao nhất + ``so_luong``.

    Returns:
        Danh sách mới theo thứ tự điểm giảm dần, mỗi phần tử có thêm ``so_luong``.
    """
    gop: dict[str, dict] = {}
    for hop in cac_hop:
        lop = hop["lop"]
        cu = gop.get(lop)
        if cu is None or hop["diem"] > cu["diem"]:
            gop[lop] = {**hop, "so_luong": 0}
        gop[lop]["so_luong"] += 1
    return sorted(gop.values(), key=lambda v: v["diem"], reverse=True)


def _crop_hop(image: Image.Image, box: list[float]) -> Image.Image | None:
    """Cắt hộp đã nới ~8% rồi kẹp vào biên ảnh gốc. ``None`` nếu crop quá nhỏ."""
    rong, cao = image.size
    x1, y1, x2, y2 = box
    rong_noi = (x2 - x1) * _NOI_HOP_TI_LE
    cao_noi = (y2 - y1) * _NOI_HOP_TI_LE
    trai = max(0, int(x1 - rong_noi))
    tren = max(0, int(y1 - cao_noi))
    phai = min(rong, int(x2 + rong_noi))
    duoi = min(cao, int(y2 + cao_noi))
    if phai - trai < 2 or duoi - tren < 2:
        return None
    return image.crop((trai, tren, phai, duoi))


def cat_va_cham_tung_vat(
    image_bytes: bytes,
    categories: list,
    *,
    classify_image_local,
) -> list[dict] | None:
    """Cắt từng vật rồi CLIP chấm từng crop.

    Args:
        image_bytes: ảnh đã qua tiền xử lý (như :func:`src.services.classifier.classify_waste` nhận).
        categories: danh mục rác (``list[CategoryOption]``) để CLIP chọn và để tra
            cờ ``is_hazardous``.
        classify_image_local: hàm chấm ảnh bằng CLIP — truyền vào để test thay giả lập.

    Returns:
        ``[{"name","category_code","so_luong","confidence","lop_yolo"}]`` theo thứ
        tự điểm YOLO giảm dần, hoặc ``None`` để đi đường cũ (cờ tắt, YOLO không
        dùng được, < 2 vật, nghi đồ điện tử, crop nghi nguy hại, ảnh hỏng).
        Vật nào CLIP dưới ngưỡng thì bị bỏ khỏi danh sách — không bịa nhãn.
    """
    settings = get_settings()

    try:
        cac_hop = local_yolo.phat_hien_co_hop(image_bytes)
    except Exception:
        # Đường này là bổ sung, không được phép làm hỏng lần phân loại — mọi lỗi
        # đều rơi về đường cũ, đúng tinh thần "mất một tầng không mất sản phẩm".
        return None
    if cac_hop is None or len(cac_hop) < 2:
        return None

    # Đồ điện tử lẫn trong ảnh → trả None cả ảnh để rơi về đường cũ (cloud + HITL).
    if any(h["lop"] in local_yolo.DO_DIEN_TU for h in cac_hop):
        return None

    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except (OSError, ValueError):
        return None

    cac_vat = _gop_trung_lop(cac_hop)[: settings.so_vat_toi_da]
    ket_qua: list[dict] = []
    for vat in cac_vat:
        crop = _crop_hop(image, vat["box"])
        if crop is None:
            continue
        tam = io.BytesIO()
        crop.save(tam, format="JPEG", quality=85)

        local = classify_image_local(tam.getvalue(), categories)
        if local is None:
            continue
        nhom = next((c for c in categories if c.code == local.category_code), None)
        # Crop nghi nguy hại → trả None CẢ ảnh, đừng trả lời các món còn lại như
        # thể chúng an toàn. Đây là chốt an toàn không được nới.
        if local.suspect_hazardous or bool(nhom and nhom.is_hazardous):
            return None
        if local.confidence < settings.clip_accept_confidence:
            continue
        ket_qua.append(
            {
                "name": local.item_name,
                "category_code": local.category_code,
                "so_luong": vat["so_luong"],
                "confidence": round(local.confidence, 4),
                "lop_yolo": vat["lop"],
            }
        )
    return ket_qua
