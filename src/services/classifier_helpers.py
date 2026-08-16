"""Hàm phụ trợ của định tuyến phân loại — không chạm tầng model.

Mọi hàm ở đây đều thuần logic/dữ liệu: đọc danh mục, ghi outcome, kiểm an toàn.
Các hàm dùng trực tiếp vision (``get_vision_client``…) nằm ở
:mod:`src.services.classifier` vì test chèn model giả vào đúng module đó.
"""

from __future__ import annotations

import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config import get_settings
from src.db.models import Classification, Media, WasteCategory
from src.services import safety
from src.services.classifier_types import ClassifyOutcome, NodeMetric
from src.services.image import phash_distance
from src.services.safety import RefusalReason
from src.services.vision import CategoryOption, VisionResult


def load_category_options(session: Session) -> list[CategoryOption]:
    """Đọc danh mục rác từ CSDL thành danh sách lựa chọn đưa vào prompt."""
    rows = session.scalars(select(WasteCategory).order_by(WasteCategory.sort_order)).all()
    return [
        CategoryOption(code=c.code, name=c.name, is_hazardous=c.is_hazardous, hint=c.clip_prompts)
        for c in rows
    ]


def _category_by_code(session: Session, code: str) -> WasteCategory | None:
    if not code:
        return None
    return session.scalar(select(WasteCategory).where(WasteCategory.code == code))


def _refuse(
    outcome: ClassifyOutcome,
    reason: RefusalReason,
    *,
    headline: str = "",
) -> ClassifyOutcome:
    """Đánh dấu từ chối trả lời, giữ lại phỏng đoán để hiện trên màn 4.4.

    Phỏng đoán **vẫn hiện** nhưng dán nhãn rõ là phỏng đoán và không kèm hướng
    dẫn xử lý — đó là điểm khác nhau giữa "thận trọng" và "vô dụng".
    """
    outcome.refused = True
    outcome.refusal_reason = str(reason)
    outcome.refusal_label_vi = safety.REFUSAL_LABELS_VI[reason]
    outcome.refusal_headline_vi = headline or safety.REFUSAL_HEADLINE_VI
    outcome.guess_item_name = outcome.guess_item_name or outcome.item_name
    outcome.guess_category_code = outcome.guess_category_code or outcome.category_code
    # Từ chối thì không chốt nhãn, và tuyệt đối không kèm hướng dẫn xử lý.
    outcome.category = None
    outcome.item_name = ""
    outcome.safety_warning = ""
    return outcome


def _quality_refusal_reason(quality_issue: str) -> RefusalReason | None:
    mapping = {
        "anh_toi": RefusalReason.ANH_TOI,
        "mo": RefusalReason.ANH_MO,
        "vat_bi_che": RefusalReason.VAT_BI_CHE,
        "nhieu_vat": RefusalReason.NHIEU_VAT,
    }
    return mapping.get(quality_issue)


def _lookup_phash_cache(session: Session, phash: str) -> tuple[Classification, int] | None:
    """Tìm lần phân loại trước của ảnh trùng hoặc gần trùng.

    Trong chung cư, cùng một loại vỏ hộp được chụp lại rất nhiều lần — đây là
    tầng rẻ nhất và cũng là tầng hay trúng nhất.
    """
    if not phash:
        return None
    max_distance = get_settings().phash_max_distance

    rows = session.execute(
        select(Classification, Media)
        .join(Media, Classification.media_id == Media.id)
        .where(
            Media.phash != "",
            Classification.refused.is_(False),
            Classification.predicted_category_id.is_not(None),
        )
        .order_by(Classification.created_at.desc())
        .limit(300)
    ).all()

    best: tuple[Classification, int] | None = None
    for classification, media in rows:
        distance = phash_distance(phash, media.phash)
        if distance <= max_distance and (best is None or distance < best[1]):
            best = (classification, distance)
            if distance == 0:
                break
    return best


def _apply_vision_result(
    session: Session,
    outcome: ClassifyOutcome,
    result: VisionResult,
    tier: str,
) -> ClassifyOutcome:
    """Ghi kết quả model vào outcome và tính ngưỡng của nhóm tương ứng."""
    outcome.tier = tier
    outcome.model = result.model
    outcome.provider = result.provider
    outcome.item_name = result.item_name
    outcome.confidence = result.confidence
    outcome.items = result.items
    outcome.suspect_hazardous = result.suspect_hazardous
    outcome.category = _category_by_code(session, result.category_code)
    outcome.min_confidence = safety.min_confidence_for(outcome.category)
    outcome.confidence_level = safety.confidence_level(outcome.confidence, outcome.min_confidence)
    outcome.safety_warning = safety.safety_warning_for(outcome.category)
    return outcome


def _goi_model(
    client: object,
    *,
    image_bytes: bytes | None,
    text_query: str,
    categories: list[CategoryOption],
    model: str,
) -> VisionResult:
    """Gọi model, tự chọn đường ảnh hay đường chữ. Lỗi để nguyên cho người gọi."""
    if image_bytes is not None:
        return client.classify_image(image_bytes, categories, model)  # type: ignore[attr-defined]
    return client.classify_text(text_query, categories, model)  # type: ignore[attr-defined]


def _finalize(
    outcome: ClassifyOutcome,
    text_query: str,
    quality_issue: str = "",
    categories: list[CategoryOption] | None = None,
) -> ClassifyOutcome:
    """Kiểm tra an toàn lần cuối trước khi dám trả lời.

    Thứ tự ưu tiên: chặn cứng → chất lượng ảnh → ngưỡng của nhóm. Chặn cứng
    đứng trước vì nó **bỏ qua confidence** hoàn toàn.

    Args:
        categories: danh mục rác của lần phân loại này, dùng để biết mã nào là
            nhóm nguy hại. Thiếu nó thì ``nhieu_nhom_khac_nhau`` giữ hành vi
            chặt như trước — không biết thì không được đoán là an toàn.
    """
    step = time.perf_counter()
    rule = safety.check_hard_block(outcome.item_name, text_query)
    outcome.nodes.append(
        NodeMetric(
            node="safety_check",
            duration_ms=int((time.perf_counter() - step) * 1000),
            meta={"hard_block": rule.code if rule else "", "danh_sach_chan_cung": len(safety.HARD_BLOCK_RULES)},
        )
    )
    if rule is not None:
        outcome.hard_block = rule
        return _refuse(outcome, RefusalReason.CHAN_CUNG, headline=safety.REFUSAL_HARD_BLOCK_VI)

    if not outcome.category:
        return _refuse(outcome, RefusalReason.KHONG_NHAN_RA)

    # Nhiều nhóm khác nhau **và trong đó có nhóm nguy hại** → một nhãn duy nhất
    # là câu trả lời nguy hiểm, từ chối **bất kể confidence**. Kiểm trước bước
    # so ngưỡng bên dưới, vì bước đó chỉ chạy khi confidence thấp và sẽ bỏ lọt
    # đúng ca này.
    #
    # Ảnh nhiều nhóm nhưng KHÔNG có nguy hại (nhựa + giấy + thuỷ tinh) thì vẫn
    # trả lời theo món chủ đạo — xem docstring của `nhieu_nhom_khac_nhau` về lý
    # do nới, và mục 4 bàn giao 02/08 về hướng xử lý gốc.
    ma_nguy_hai = {c.code for c in categories if c.is_hazardous} if categories is not None else None
    if safety.nhieu_nhom_khac_nhau(outcome.items, ma_nguy_hai):
        return _refuse(outcome, RefusalReason.NHIEU_VAT)

    # Model khai "nhiều món chồng lên nhau" NHƯNG không liệt kê món nào → không
    # có gì để kiểm xem chúng có cùng nhóm hay không, nên không được đoán. Chặn
    # **bất kể confidence**; trước 02/08 nhánh này nằm lọt bên trong
    # `confidence < min_confidence` nên nhieu_vat kèm confidence 0,9 đi thẳng
    # qua cả hai cửa.
    #
    # Có liệt kê thì để `nhieu_nhom_khac_nhau` ở trên phán: nhiều món CÙNG một
    # nhóm vẫn trả lời bình thường — ba cái chai nhựa thì vẫn chỉ là nhựa tái
    # chế, từ chối ở đó là khắt khe vô ích.
    if quality_issue == RefusalReason.NHIEU_VAT.value and not outcome.items:
        return _refuse(outcome, RefusalReason.NHIEU_VAT)

    if outcome.confidence < outcome.min_confidence:
        quality_reason = _quality_refusal_reason(quality_issue)
        if quality_reason is not None:
            return _refuse(outcome, quality_reason)
        if outcome.category.is_hazardous or outcome.suspect_hazardous:
            return _refuse(outcome, RefusalReason.NGHI_NGUY_HAI, headline=safety.REFUSAL_HAZARD_VI)
        return _refuse(outcome, RefusalReason.DUOI_NGUONG)

    return outcome
