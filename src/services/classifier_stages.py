"""Các bước chạy theo tầng của định tuyến phân loại.

Tách khỏi :mod:`src.services.classifier` để giữ mỗi file dưới ngưỡng ~300 dòng.
Các hàm ở đây nhận hàm vision qua **tham số** thay vì import trực tiếp:
:mod:`src.services.classifier` truyền vào đúng hàm đã bị test chèn model giả
(monkeypatch), nên hành vi khi chạy test không đổi.
"""

from __future__ import annotations

import logging
import time

from sqlalchemy.orm import Session

from src.config import ModelTier, get_settings
from src.db.models import WasteCategory
from src.services import safety
from src.services.classifier_helpers import (
    _apply_vision_result,
    _category_by_code,
    _finalize,
    _goi_model,
    _lookup_phash_cache,
    _refuse,
)
from src.services.classifier_types import (
    TIER_T0_CACHE,
    TIER_T05_LOCAL,
    TIER_T1,
    TIER_T2,
    ClassifyOutcome,
    NodeMetric,
)
from src.services.safety import RefusalReason
from src.services.vision import CategoryOption, VisionUnavailableError, local_yolo

logger = logging.getLogger(__name__)


def chay_t0_cache(
    session: Session,
    outcome: ClassifyOutcome,
    *,
    image_bytes: bytes | None,
    image_phash: str,
    started: float,
) -> bool:
    """Tầng T0 — cache pHash. Trả về ``True`` nếu trúng cache (đã điền outcome)."""
    if image_bytes is None or not image_phash:
        return False
    step = time.perf_counter()
    hit = _lookup_phash_cache(session, image_phash)
    duration = int((time.perf_counter() - step) * 1000)
    if hit is None:
        outcome.nodes.append(NodeMetric(node="cache_lookup", duration_ms=duration, meta={"hit": False}))
        return False
    previous, distance = hit
    outcome.nodes.append(
        NodeMetric(
            node="cache_lookup",
            duration_ms=duration,
            cache_hits=1,
            meta={"phash_distance": distance, "source_classification_id": previous.id},
        )
    )
    outcome.tier = TIER_T0_CACHE
    outcome.model = "cache"
    outcome.provider = "cache"
    outcome.item_name = previous.item_name
    outcome.confidence = previous.confidence
    outcome.category = session.get(WasteCategory, previous.predicted_category_id)
    outcome.min_confidence = safety.min_confidence_for(outcome.category)
    outcome.confidence_level = safety.confidence_level(outcome.confidence, outcome.min_confidence)
    outcome.safety_warning = safety.safety_warning_for(outcome.category)
    outcome.cache_source_id = previous.id
    outcome.latency_ms = int((time.perf_counter() - started) * 1000)
    return True


def chay_t05_yolo(outcome: ClassifyOutcome, *, image_bytes: bytes | None) -> bool:
    """Tầng T0.5b — YOLO giơ cờ đồ điện tử. Trả về ``True`` nếu NGHI.

    Hàm này **không bao giờ chốt nhãn**. Nó chỉ trả một cờ, và cờ đó được mang
    tới tận ``should_escalate_to_t2`` để ép hỏi model mạnh hơn. Xem ADR-0011.
    """
    settings = get_settings()
    if image_bytes is None or not settings.yolo_enabled:
        return False
    step = time.perf_counter()
    nghi = False
    cac_lop: list[str] = []
    try:
        nghi, cac_vat = local_yolo.nghi_do_dien_tu(image_bytes)
        cac_lop = [v.get("lop", "?") for v in cac_vat]
    except Exception as exc:
        logger.warning("Tầng YOLO lỗi không ngờ: %s. Không giơ cờ.", exc)
    duration = int((time.perf_counter() - step) * 1000)
    outcome.nodes.append(
        NodeMetric(
            node="local_yolo",
            duration_ms=duration,
            meta={"nghi_do_dien_tu": nghi, "cac_lop_phat_hien": cac_lop},
        )
    )
    return nghi


def chay_t05_local(
    session: Session,
    outcome: ClassifyOutcome,
    *,
    image_bytes: bytes | None,
    categories: list[CategoryOption],
    text_query: str,
    started: float,
    classify_image_local: object,
    nghi_nguy_hai_local: bool = False,
) -> tuple[bool, bool]:
    """Tầng T0.5 — model local. Trả về ``(chot, nghi_nguy_hai_clip)``: chốt được chưa, và CLIP có nghi nguy hại không (mang xuống T1/T2 kể cả khi không chốt)."""
    settings = get_settings()
    if image_bytes is None or not settings.local_model_enabled:
        return (False, False)
    step = time.perf_counter()
    local = classify_image_local(image_bytes, categories)  # type: ignore[operator]
    duration = int((time.perf_counter() - step) * 1000)
    if local is None:
        outcome.nodes.append(
            NodeMetric(node="local_model", status="skipped", duration_ms=duration, meta={"reason": "khong_san_sang"})
        )
        return (False, False)

    category = _category_by_code(session, local.category_code)
    is_hazard_related = local.suspect_hazardous or bool(category and category.is_hazardous)
    blocked_by_policy = is_hazard_related and settings.local_never_decides_hazardous
    # Cờ YOLO nghi đồ điện tử chặn CLIP chốt: model local không được chốt khi có
    # nghi ngờ nguy hại, và đồ điện tử là nghi ngờ nguy hại. Để CLIP chốt "giấy"
    # trong khi YOLO nghi có laptop là vứt đi cờ vừa tốn 100 ms dựng lên.
    accepted = (
        local.confidence >= settings.clip_accept_confidence
        and not blocked_by_policy
        and not nghi_nguy_hai_local
    )
    outcome.nodes.append(
        NodeMetric(
            node="local_model",
            duration_ms=duration,
            meta={
                "confidence": round(local.confidence, 4),
                "nguong_chap_nhan": settings.clip_accept_confidence,
                "chot_nhan": accepted,
                "chan_vi_nghi_nguy_hai": blocked_by_policy,
                "chan_vi_yolo_nghi_dien_tu": nghi_nguy_hai_local,
            },
        )
    )
    if not accepted:
        return (False, is_hazard_related)

    _apply_vision_result(session, outcome, local, TIER_T05_LOCAL)
    outcome.latency_ms = int((time.perf_counter() - started) * 1000)
    _finalize(outcome, text_query, categories=categories)
    return (True, is_hazard_related)


def chay_t1_t2(
    session: Session,
    outcome: ClassifyOutcome,
    *,
    image_bytes: bytes | None,
    text_query: str,
    categories: list[CategoryOption],
    started: float,
    get_vision_client: object,
    get_tier_model: object,
    get_tier_provider: object,
    nghi_nguy_hai_local: bool = False,
) -> ClassifyOutcome:
    """Tầng T1 → (nếu cần) T2, trả về outcome đã finalize hoặc đã từ chối.

    Mỗi tầng có nhà cung cấp riêng (xem ``config.resolve_provider``): T1 có
    thể chạy NVIDIA trong khi T2 chạy Gemini. Vì vậy phải lấy client theo
    tầng, không dùng chung một client cho cả hai — cạn quota một nhà cung cấp
    thì tầng còn lại vẫn sống.
    """
    di_thang_t2 = (
        get_settings().route_electronics_to_t2
        and nghi_nguy_hai_local
        and image_bytes is not None
        and bool(get_tier_model("t2"))
    )
    first_tier: ModelTier = (
        "t2" if di_thang_t2 else ("t1" if image_bytes is not None else ("text" if get_tier_model("text") else "t1"))
    )
    model_first = get_tier_model(first_tier)
    provider_first = get_tier_provider(first_tier)
    model_t2 = get_tier_model("t2")
    provider_t2 = get_tier_provider("t2")

    try:
        client = get_vision_client(first_tier)
    except VisionUnavailableError as exc:
        outcome.nodes.append(NodeMetric(node="classify_waste", status="error", error_type=exc.code))
        outcome.latency_ms = int((time.perf_counter() - started) * 1000)
        return _refuse(outcome, RefusalReason.MODEL_LOI, headline=exc.message_vi)

    # Cùng model **trên cùng một nhà cung cấp** thì gọi lại chỉ tốn tiền mà không
    # có ý kiến thứ hai. Khác nhà cung cấp thì dù trùng tên model vẫn là hai
    # đường độc lập, vẫn đáng gọi.
    t2_khac_t1 = (provider_t2, model_t2) != (provider_first, model_first)
    t2_da_dung_de_cuu = False
    cuu_khi_t2_hong = False
    provider_cuu_t1 = ""
    tier_ket_qua = TIER_T2 if di_thang_t2 else TIER_T1
    if di_thang_t2:
        outcome.escalation_reason = "T0.5 nghi đồ điện tử — đi thẳng T2, bỏ T1 (mù đồ điện tử)"

    step = time.perf_counter()
    try:
        result = _goi_model(
            client, image_bytes=image_bytes, text_query=text_query, categories=categories, model=model_first
        )
    except (VisionUnavailableError, ValueError) as exc:
        code = getattr(exc, "code", "VISION-500")
        outcome.nodes.append(
            NodeMetric(
                node="classify_waste",
                status="error",
                duration_ms=int((time.perf_counter() - step) * 1000),
                llm_calls=1,
                error_type=code,
                meta={
                    "tier": TIER_T2 if di_thang_t2 else TIER_T1,
                    "provider": provider_first,
                    "model": model_first,
                },
            )
        )
        message = getattr(exc, "message_vi", "Hệ thống nhận diện đang gặp sự cố.")

        result = None
        if di_thang_t2:
            # Đi thẳng T2 mà T2 chết: lui về T1 trước khi từ chối. T1 mù đồ điện
            # tử nhưng vẫn ra nhãn để người duyệt xử — còn hơn bỏ trống cả lần.
            model_t1 = get_tier_model("t1")
            if model_t1:
                step = time.perf_counter()
                provider_t1 = get_tier_provider("t1")
                try:
                    result = _goi_model(
                        get_vision_client("t1"),
                        image_bytes=image_bytes,
                        text_query=text_query,
                        categories=categories,
                        model=model_t1,
                    )
                except (VisionUnavailableError, ValueError) as exc_t1:
                    outcome.nodes.append(
                        NodeMetric(
                            node="classify_waste_t1",
                            status="error",
                            duration_ms=int((time.perf_counter() - step) * 1000),
                            llm_calls=1,
                            error_type=getattr(exc_t1, "code", "VISION-500"),
                            meta={"provider": provider_t1, "model": model_t1, "ly_do": "cuu_khi_t2_hong"},
                        )
                    )
                else:
                    cuu_khi_t2_hong = True
                    provider_cuu_t1 = provider_t1
                    outcome.nodes.append(
                        NodeMetric(
                            node="classify_waste_t1",
                            duration_ms=int((time.perf_counter() - step) * 1000),
                            tokens_in=result.usage.tokens_in,
                            tokens_out=result.usage.tokens_out,
                            image_tokens=result.usage.image_tokens,
                            cost_usd=result.usage.cost_usd,
                            llm_calls=1,
                            meta={
                                "provider": result.provider or provider_t1,
                                "model": result.model,
                                "ly_do": "cuu_khi_t2_hong",
                                "confidence": round(result.confidence, 4),
                            },
                        )
                    )
            if result is not None:
                tier_ket_qua = TIER_T1
                outcome.escalation_reason = (
                    f"T2 lỗi ({code}) — lui về T1 để cứu (vẫn kèm nghi ngờ đồ điện tử)"
                )
        else:
            # T1 chết KHÔNG được kéo cả lần phân loại chết theo — lời hứa của
            # ADR-0006 "mất một nguồn chỉ mất một tầng". Đo trên bản deploy:
            # llama-3.2-11b ở T1 trả JSON hỏng (VISION-500) mọi lần chụp, trong
            # khi Gemini ở T2 vẫn chạy.
            if model_t2 and t2_khac_t1:
                step = time.perf_counter()
                try:
                    result = _goi_model(
                        get_vision_client("t2"),
                        image_bytes=image_bytes,
                        text_query=text_query,
                        categories=categories,
                        model=model_t2,
                    )
                except (VisionUnavailableError, ValueError) as exc_t2:
                    outcome.nodes.append(
                        NodeMetric(
                            node="classify_waste_t2",
                            status="error",
                            duration_ms=int((time.perf_counter() - step) * 1000),
                            llm_calls=1,
                            error_type=getattr(exc_t2, "code", "VISION-500"),
                            meta={"provider": provider_t2, "model": model_t2, "ly_do": "cuu_khi_t1_hong"},
                        )
                    )

            if result is not None:
                t2_da_dung_de_cuu = True
                tier_ket_qua = TIER_T2
                outcome.escalation_reason = f"T1 lỗi ({code}) — chuyển sang nhà cung cấp của T2"

        if result is None:
            outcome.latency_ms = int((time.perf_counter() - started) * 1000)
            return _refuse(outcome, RefusalReason.MODEL_LOI, headline=message)

    _apply_vision_result(session, outcome, result, tier_ket_qua)
    outcome.cost_usd += result.usage.cost_usd
    outcome.price_known = outcome.price_known and result.usage.price_known
    outcome.nodes.append(
        NodeMetric(
            node="classify_waste",
            duration_ms=int((time.perf_counter() - step) * 1000),
            tokens_in=result.usage.tokens_in,
            tokens_out=result.usage.tokens_out,
            image_tokens=result.usage.image_tokens,
            cost_usd=result.usage.cost_usd,
            llm_calls=1,
            meta={
                "tier": tier_ket_qua,
                "provider": result.provider
                or (
                    provider_cuu_t1
                    if cuu_khi_t2_hong
                    else (provider_t2 if t2_da_dung_de_cuu else provider_first)
                ),
                "model": result.model,
                "confidence": round(result.confidence, 4),
                "nguong_nhom": round(outcome.min_confidence, 4),
                **({"cuu_khi_t1_hong": True} if t2_da_dung_de_cuu else {}),
                **({"cuu_khi_t2_hong": True} if cuu_khi_t2_hong else {}),
            },
        )
    )

    escalation = safety.should_escalate_to_t2(
        outcome.confidence,
        outcome.min_confidence,
        # Sự nghi ngờ của T0.5 phải sống tới đây. T1 là tầng MÙ đồ điện tử, nên
        # nếu chỉ hỏi `result.suspect_hazardous` thì đúng ca cần leo T2 nhất lại
        # im lặng — xem CONTEXT của gói P33.
        result.suspect_hazardous or nghi_nguy_hai_local,
        result.quality_issue,
        items=result.items,
        co_anh=image_bytes is not None,
    )
    # Đã phải nhờ T2 cứu vì T1 hỏng thì kết quả đang cầm CHÍNH LÀ của T2 — gọi
    # lại lần nữa chỉ tốn thêm một lượt quota để nhận đúng câu trả lời đó.
    if escalation and model_t2 and t2_khac_t1 and not t2_da_dung_de_cuu:
        outcome.escalation_reason = escalation
        step = time.perf_counter()
        try:
            # Client T2 dựng ngay tại đây: provider của T2 có thể khác T1 và có
            # thể thiếu key, lỗi đó phải rơi vào cùng nhánh "T2 hỏng" bên dưới.
            client_t2 = get_vision_client("t2")
            if image_bytes is not None:
                result_t2 = client_t2.classify_image(image_bytes, categories, model_t2)
            else:
                result_t2 = client_t2.classify_text(text_query, categories, model_t2)
        except (VisionUnavailableError, ValueError) as exc:
            # T2 lỗi thì giữ kết quả T1 và để bước kiểm ngưỡng bên dưới quyết
            # định — không được im lặng nâng cấp độ tin cậy.
            outcome.nodes.append(
                NodeMetric(
                    node="classify_waste_t2",
                    status="error",
                    duration_ms=int((time.perf_counter() - step) * 1000),
                    llm_calls=1,
                    error_type=getattr(exc, "code", "VISION-500"),
                    meta={"provider": provider_t2, "model": model_t2},
                )
            )
        else:
            _apply_vision_result(session, outcome, result_t2, TIER_T2)
            outcome.cost_usd += result_t2.usage.cost_usd
            outcome.price_known = outcome.price_known and result_t2.usage.price_known
            outcome.nodes.append(
                NodeMetric(
                    node="classify_waste_t2",
                    duration_ms=int((time.perf_counter() - step) * 1000),
                    tokens_in=result_t2.usage.tokens_in,
                    tokens_out=result_t2.usage.tokens_out,
                    image_tokens=result_t2.usage.image_tokens,
                    cost_usd=result_t2.usage.cost_usd,
                    llm_calls=1,
                    meta={
                        "tier": TIER_T2,
                        "provider": result_t2.provider or provider_t2,
                        "model": result_t2.model,
                        "ly_do_escalate": escalation,
                        "confidence": round(result_t2.confidence, 4),
                    },
                )
            )
        outcome.suspect_hazardous = outcome.suspect_hazardous or result.suspect_hazardous

    outcome.latency_ms = int((time.perf_counter() - started) * 1000)
    return _finalize(outcome, text_query, quality_issue=result.quality_issue, categories=categories)
