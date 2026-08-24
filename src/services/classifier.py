"""Định tuyến model 4 tầng cho việc phân loại rác.

| Tầng | Dùng khi | Chi phí |
|---|---|---|
| ``t0_cache`` | ảnh trùng/gần trùng đã phân loại (pHash) | $0 |
| ``t0_5_local`` | CLIP zero-shot chạy trên CPU, rất chắc và không phải nhóm nguy hại | $0 |
| ``t1_mini`` | model vision rẻ — phần lớn lưu lượng | thấp |
| ``t2_full`` | confidence thấp **hoặc nghi rác nguy hại** | cao |

Mỗi tầng đọc nhà cung cấp riêng từ cấu hình, nên T1 chạy được trên NVIDIA trong
khi T2 chạy Gemini — hết quota một nơi không làm đứng cả sản phẩm.

Module này giữ **lớp điều phối** (:func:`classify_waste`) và tập trung các tên
dùng chung để test chèn model giả bằng ``monkeypatch`` vào đúng module này.
Việc thực thi từng tầng nằm ở :mod:`src.services.classifier_stages`, các kiểu
dữ liệu ở :mod:`src.services.classifier_types`, các hàm phụ ở
:mod:`src.services.classifier_helpers`.

Mọi bước đều sinh một :class:`NodeMetric` để màn Agent Run (spec 4.15) và trang
Vận hành (4.16) có số liệu thật, không phải số ước.
"""

from __future__ import annotations

import time

from sqlalchemy.orm import Session

from src.config import get_settings
from src.services import phan_loai_nhieu_vat, safety
from src.services.classifier_helpers import (
    _apply_vision_result,
    _category_by_code,
    _finalize,
    _refuse,
    load_category_options,
)
from src.services.classifier_stages import chay_t0_cache, chay_t05_local, chay_t05_yolo, chay_t1_t2
from src.services.classifier_types import (
    TIER_LABELS_VI,
    TIER_T0_CACHE,
    TIER_T05_LOCAL,
    TIER_T1,
    TIER_T2,
    ClassifyOutcome,
    NodeMetric,
)
from src.services.safety import RefusalReason
from src.services.vision import (
    Usage,
    VisionResult,
    classify_image_local,
    get_tier_model,
    get_tier_provider,
    get_vision_client,
)

__all__ = [
    "TIER_T0_CACHE",
    "TIER_T05_LOCAL",
    "TIER_T1",
    "TIER_T2",
    "TIER_LABELS_VI",
    "NodeMetric",
    "ClassifyOutcome",
    "classify_waste",
    "load_category_options",
    "_category_by_code",
]


def classify_waste(
    session: Session,
    *,
    image_bytes: bytes | None = None,
    image_phash: str = "",
    text_query: str = "",
) -> ClassifyOutcome:
    """Chạy trọn định tuyến 4 tầng cho một món rác.

    Args:
        session: phiên CSDL để đọc danh mục và cache.
        image_bytes: ảnh **đã qua tiền xử lý** (:func:`src.services.image.preprocess_image`).
            Không bao giờ truyền ảnh gốc vào đây.
        image_phash: pHash của ảnh đã xử lý, dùng cho cache tầng T0.
        text_query: câu mô tả bằng chữ, dùng khi không có ảnh.

    Returns:
        :class:`ClassifyOutcome` — có thể ở trạng thái từ chối trả lời, và đó là
        một kết quả hợp lệ chứ không phải lỗi.
    """
    settings = get_settings()
    outcome = ClassifyOutcome(prompt_version=settings.prompt_version)
    started = time.perf_counter()

    # --- Bước 1: chặn cứng theo câu chữ người dùng, trước mọi lệnh gọi model ---
    step = time.perf_counter()
    rule = safety.check_hard_block(text_query)
    outcome.nodes.append(
        NodeMetric(
            node="safety_precheck",
            duration_ms=int((time.perf_counter() - step) * 1000),
            meta={"hard_block": rule.code if rule else ""},
        )
    )
    if rule is not None:
        outcome.hard_block = rule
        outcome.guess_item_name = rule.label_vi
        _refuse(outcome, RefusalReason.CHAN_CUNG, headline=safety.REFUSAL_HARD_BLOCK_VI)
        outcome.latency_ms = int((time.perf_counter() - started) * 1000)
        return outcome

    categories = load_category_options(session)

    # --- Bước 2: T0 — cache pHash ---
    if chay_t0_cache(session, outcome, image_bytes=image_bytes, image_phash=image_phash, started=started):
        return outcome

    # --- Bước 3: T0.5 — model local, chỉ chốt khi rất chắc và không nguy hại ---
    # Chạy YOLO TRƯỚC CLIP: rẻ hơn việc phát hiện muộn, và cờ này còn phải đi
    # tiếp tới T1/T2 dù CLIP có chốt được hay không.
    nghi_dien_tu = chay_t05_yolo(outcome, image_bytes=image_bytes)

    # --- Bước 3.5: phân loại TỪNG VẬT (hướng A) --------------------------
    # Ảnh nhiều vật mà CLIP chấm cả khung hình thì điểm rơi dưới ngưỡng (trace
    # #301: 7 chai + bàn phím + cốc → 0,1356) → leo cloud → hỏng/từ chối. Cắt
    # từng crop rồi CLIP chấm từng cái: crop chỉ có một vật nên điểm cao hẳn,
    # chốt được ngay tại chỗ, $0. Cờ mặc định TẮT — chưa chuẩn ngưỡng xong.
    # ⛔ Không chạy khi YOLO nghi đồ điện tử: path này không bao giờ được chốt
    # nhãn khi có nghi ngờ nguy hại.
    if settings.phan_loai_tung_vat and image_bytes is not None and not nghi_dien_tu:
        cac_vat_tung_cai = phan_loai_nhieu_vat.cat_va_cham_tung_vat(
            image_bytes=image_bytes,
            categories=categories,
            classify_image_local=classify_image_local,
        )
        if cac_vat_tung_cai is not None and len(cac_vat_tung_cai) >= 2:
            chac_nhat = max(cac_vat_tung_cai, key=lambda m: m["confidence"])
            _apply_vision_result(
                session,
                outcome,
                VisionResult(
                    item_name=chac_nhat["name"],
                    category_code=chac_nhat["category_code"],
                    confidence=chac_nhat["confidence"],
                    items=cac_vat_tung_cai,
                    model=f"yolo_crop+clip ({settings.clip_model_name})",
                    provider="local_yolo_clip",
                    usage=Usage(cost_usd=0.0, price_known=True),
                ),
                TIER_T05_LOCAL,
            )
            outcome.nodes.append(
                NodeMetric(
                    node="phan_loai_tung_vat",
                    meta={
                        "so_vat": len(cac_vat_tung_cai),
                        "cac_lop": [m["lop_yolo"] for m in cac_vat_tung_cai],
                    },
                )
            )
            outcome.latency_ms = int((time.perf_counter() - started) * 1000)
            return _finalize(outcome, text_query, categories=categories)

    chot_local, nghi_nguy_hai_clip = chay_t05_local(
        session,
        outcome,
        image_bytes=image_bytes,
        categories=categories,
        text_query=text_query,
        started=started,
        classify_image_local=classify_image_local,
        # Cờ YOLO chặn CLIP chốt: model local không được chốt khi có nghi ngờ
        # nguy hại, và đồ điện tử là nghi ngờ nguy hại.
        nghi_nguy_hai_local=nghi_dien_tu,
    )
    if chot_local:
        return outcome
    # Nghi ngờ nguy hại đến từ HAI nguồn local: YOLO (đồ điện tử) HOẶC CLIP
    # (cosine rơi vào nhóm nguy hại). Trước đây chỉ YOLO được mang xuống, nên ca
    # CLIP nghi mà YOLO trượt vẫn vào T1 mù rồi timeout. Gộp cả hai xuống T1/T2.
    nghi_nguy_hai = nghi_dien_tu or nghi_nguy_hai_clip

    # --- Bước 4: T1 → (nếu cần) T2 ---
    return chay_t1_t2(
        session,
        outcome,
        image_bytes=image_bytes,
        text_query=text_query,
        categories=categories,
        started=started,
        get_vision_client=get_vision_client,
        get_tier_model=get_tier_model,
        get_tier_provider=get_tier_provider,
        nghi_nguy_hai_local=nghi_nguy_hai,
    )
