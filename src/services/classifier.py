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
from src.services import safety
from src.services.classifier_helpers import _category_by_code, _refuse, load_category_options
from src.services.classifier_stages import chay_t0_cache, chay_t05_local, chay_t1_t2
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
    if chay_t05_local(
        session,
        outcome,
        image_bytes=image_bytes,
        categories=categories,
        text_query=text_query,
        started=started,
        classify_image_local=classify_image_local,
    ):
        return outcome

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
    )
