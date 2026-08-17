"""Dựng phản hồi thiết bị phân loại (CP2) từ kết quả phân loại đã có.

Thuần hàm: **không gọi model, không chạm CSDL, không chạm mạng** — nhận kết quả
phân loại (:class:`src.services.classifier_types.ClassifyOutcome`) do pipeline
hiện có sinh ra, trả về đúng hợp đồng thiết bị đã chốt trong báo cáo tuần:

.. code-block:: json

    {
        "item_id": "…",
        "label": "…",
        "confidence": 0.94,
        "route": "plastic|metal|paper|other",
        "review_required": false,
        "model_version": "…"
    }

Kiến trúc (ADR-0012): firmware chỉ THỰC THI ``route``, không tự đặt ngưỡng và
không tự quyết nhãn. Hai trường là hai thứ **tách bạch**:

- ``label`` — máy chủ NGHĨ món này là gì (mã nhóm rác, hoặc ``UNKNOWN`` khi từ
  chối / không chắc);
- ``route`` — servo quay ngăn nào (``plastic`` | ``metal`` | ``paper`` |
  ``other``).

Quy tắc:

1. Có nhãn, đủ tự tin, không nguy hại → ``route`` theo bảng ánh xạ
   (:func:`src.services.dinh_tuyen_ngan.nhom_rac_den_ngan`),
   ``review_required=False``.
2. Từ chối / không chắc → ``label="UNKNOWN"``, ``route="other"``,
   ``review_required=True``. ⛔ ``UNKNOWN`` KHÔNG được đổi thành ``other`` ở phần
   NHÃN — ``other`` chỉ là ngăn vật lý đổ vào để dây chuyền không đứng.
3. Nhóm nguy hại → ``review_required=True`` LUÔN, bất kể confidence cao đến đâu;
   ``route="other"`` (ngăn an toàn).
4. ``model_version`` lấy từ thông tin prompt/model mà outcome mang sẵn; không
   có thì trả chuỗi rỗng — không bịa số phiên bản.
"""

from __future__ import annotations

from typing import Final
from uuid import uuid4

from src.services.classifier_types import ClassifyOutcome
from src.services.dinh_tuyen_ngan import NGAN_OTHER, nhom_rac_den_ngan

# Nhãn chuẩn cho ca máy chủ từ chối / không chắc. Giữ riêng với ``NGAN_OTHER``:
# nhãn nói máy chủ nghĩ gì, ngăn nói servo quay đâu.
LABEL_UNKNOWN: Final[str] = "UNKNOWN"


def dung_phan_hoi(outcome: ClassifyOutcome, item_id: str = "") -> dict:
    """Dựng phản hồi thiết bị từ kết quả phân loại đã có.

    Args:
        outcome: kết quả do pipeline phân loại sinh ra. Có thể đang ở trạng thái
            từ chối trả lời — đó là một kết quả hợp lệ, không phải lỗi.
        item_id: mã món rác do thiết bị gửi (đã được giữ nguyên, xem
            :func:`sinh_item_id`). Thiết bị không gửi thì để rỗng — gói sau sẽ
            sinh bằng :func:`sinh_item_id` trước khi gọi hàm này.

    Returns:
        Dict đúng hợp đồng thiết bị đã chốt (sáu khoá nêu ở docstring module).
    """
    category = outcome.category
    model_version = outcome.prompt_version or outcome.model or ""

    # Quy tắc 2 — từ chối / không chắc (kể cả khi outcome không có nhãn):
    # nhãn UNKNOWN, route về ngăn an toàn để dây chuyền không đứng.
    if outcome.refused or category is None:
        return {
            "item_id": item_id,
            "label": LABEL_UNKNOWN,
            "confidence": round(outcome.confidence, 4),
            "route": NGAN_OTHER,
            "review_required": True,
            "model_version": model_version,
        }

    # Quy tắc 3 — nhóm nguy hại: review_required LUÔN bật, bất kể confidence.
    # Route cứng ``other`` chứ không uỷ thác bảng ánh xạ: nhóm nguy hại không
    # bao giờ được đổ vào ngăn thu hồi, dù sau này có ai thêm vào bảng.
    if category.is_hazardous:
        return {
            "item_id": item_id,
            "label": category.code,
            "confidence": round(outcome.confidence, 4),
            "route": NGAN_OTHER,
            "review_required": True,
            "model_version": model_version,
        }

    # Quy tắc 1 — ca thường: đủ tự tin, không nguy hại.
    return {
        "item_id": item_id,
        "label": category.code,
        "confidence": round(outcome.confidence, 4),
        "route": nhom_rac_den_ngan(category.code),
        "review_required": False,
        "model_version": model_version,
    }


def sinh_item_id(thiet_bi_gui: str = "") -> str:
    """Sinh ``item_id`` cho một món rác khi thiết bị không gửi.

    Thiết bị **có** gửi thì giữ nguyên chuỗi của nó (chỉ bỏ khoảng trắng thừa
    hai đầu) — nó là khoá để thử lại không tạo bản ghi trùng (idempotency ở gói
    sau). Thiết bị **không** gửi thì sinh bằng ``uuid4``.

    Args:
        thiet_bi_gui: chuỗi ``item_id`` thiết bị gửi kèm, mặc định rỗng.

    Returns:
        Chuỗi ``item_id`` dùng cho bản ghi lần này.
    """
    if thiet_bi_gui.strip():
        return thiet_bi_gui.strip()
    return str(uuid4())


# ─── Idempotency (GHI CHÚ, CHƯA LÀM — thuộc gói sau khi gộp code nhóm) ───────
#
# Cùng ``item_id`` gửi lại thì PHẢI trả kết quả cũ, không tạo bản ghi phân loại
# thứ hai. Cách làm dự kiến: tra ``Classification`` gần nhất theo ``item_id``
# lưu trong một trường văn bản SẴN CÓ (không thêm cột), ví dụ ``text_query`` với
# tiền tố cố định ``item_id:`` — y hệt cách router cũ đã làm.
#
# Phần này ĐỤNG CSDL và router nên để sau lần gộp code nhóm; file này chỉ dựng
# phần lõi thuần hàm để router gọi. Đừng làm trước.
