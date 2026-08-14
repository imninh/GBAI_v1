"""T0.5 (YOLO) nghi đồ điện tử thì đi thẳng T2, bỏ lượt T1 mù.

Số đo 13/08 cho thấy T1 (``nvidia/llama-3.2-90b``) p50 ~25s, 94% ảnh vẫn leo T2,
và mù đồ điện tử (03/08: 0/6). Khi YOLO đã giơ cờ ``nghi_nguy_hai_local`` thì hỏi
T1 chỉ tốn một lượt gọi chậm rồi vẫn leo T2 — cờ ``route_electronics_to_t2`` cho
đi thẳng T2. Cờ tắt = hành vi cũ y hệt.
"""

from __future__ import annotations

import os

from src.config import reset_settings_cache
from src.services.classifier_stages import chay_t1_t2
from src.services.classifier_types import TIER_T2, ClassifyOutcome
from src.services.vision import CategoryOption
from tests.conftest import FakeVisionClient, make_result

TIER_MODEL = {"t1": "M_T1", "t2": "M_T2", "text": "M_TEXT"}


def _stubs() -> tuple[FakeVisionClient, dict]:
    """Dựng client giả ghi lại lần gọi và các hàm nạp model/provider."""
    client = FakeVisionClient(
        results=[make_result(confidence=0.91, suspect_hazardous=False), make_result(confidence=0.91, suspect_hazardous=False)]
    )
    deps = {
        "get_vision_client": lambda _tier: client,
        "get_tier_model": lambda tier: TIER_MODEL[tier],
        "get_tier_provider": lambda tier: f"prov_{tier}",
    }
    return client, deps


def _goi(session, image_bytes: bytes | None, nghi_nguy_hai_local: bool, **kw) -> tuple[ClassifyOutcome, FakeVisionClient]:
    client, deps = _stubs()
    deps.update(kw)
    outcome = ClassifyOutcome(prompt_version="test")
    chay_t1_t2(
        session,
        outcome,
        image_bytes=image_bytes,
        text_query="",
        categories=[CategoryOption(code="x", name="X")],
        started=0.0,
        **deps,
        nghi_nguy_hai_local=nghi_nguy_hai_local,
    )
    return outcome, client


def test_dien_tu_goi_thang_t2(db_session):
    outcome, client = _goi(db_session, image_bytes=b"x", nghi_nguy_hai_local=True)

    assert [(kind, model) for kind, model in client.calls] == [("image", "M_T2")]
    assert "đi thẳng T2" in outcome.escalation_reason
    assert outcome.tier == TIER_T2


def test_khong_dien_tu_van_t1_truoc(db_session):
    outcome, client = _goi(db_session, image_bytes=b"x", nghi_nguy_hai_local=False)

    assert client.calls[0] == ("image", "M_T1")
    assert outcome.escalation_reason == ""


def test_co_the_tat_bang_co(db_session):
    os.environ["ROUTE_ELECTRONICS_TO_T2"] = "false"
    reset_settings_cache()
    try:
        _, client = _goi(db_session, image_bytes=b"x", nghi_nguy_hai_local=True)
    finally:
        del os.environ["ROUTE_ELECTRONICS_TO_T2"]
        reset_settings_cache()

    assert client.calls[0] == ("image", "M_T1")


def test_dien_tu_van_can_co_anh(db_session):
    _, client = _goi(db_session, image_bytes=None, nghi_nguy_hai_local=True)

    assert client.calls[0] == ("text", "M_TEXT")
