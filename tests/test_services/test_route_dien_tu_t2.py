"""T0.5 (YOLO) nghi đồ điện tử thì đi thẳng T2, bỏ lượt T1 mù.

Số đo 13/08 cho thấy T1 (``nvidia/llama-3.2-90b``) p50 ~25s, 94% ảnh vẫn leo T2,
và mù đồ điện tử (03/08: 0/6). Khi YOLO đã giơ cờ ``nghi_nguy_hai_local`` thì hỏi
T1 chỉ tốn một lượt gọi chậm rồi vẫn leo T2 — cờ ``route_electronics_to_t2`` cho
đi thẳng T2. Cờ tắt = hành vi cũ y hệt.
"""

from __future__ import annotations

import os

from src.config import reset_settings_cache
from src.services import classifier
from src.services.classifier_stages import chay_t1_t2
from src.services.classifier_types import TIER_T2, ClassifyOutcome
from src.services.vision import CategoryOption, local_yolo
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


def test_clip_nghi_ma_yolo_truot_thi_van_di_thang_t2(db_session, monkeypatch) -> None:
    """CLIP nghi nguy hại mà YOLO trượt (không giơ cờ) vẫn phải đi thẳng T2.

    Trước khi gộp cờ, chỉ mỗi ``nghi_dien_tu`` của YOLO được mang xuống T1/T2:
    ca CLIP nghi (cosine rơi vào nhóm nguy hại) mà YOLO trượt vẫn rơi vào T1 mù
    rồi timeout. Giờ cả hai nguồn local được OR lại thành ``nghi_nguy_hai``.
    """
    monkeypatch.setenv("YOLO_ENABLED", "true")
    reset_settings_cache()
    # YOLO chạy thật nhưng TRƯỢT — không phát hiện gì, không giơ cờ.
    monkeypatch.setattr(local_yolo, "phat_hien", lambda anh: [])
    # CLIP nghi nguy hại (suspect_hazardous=True) nhưng confidence dưới ngưỡng
    # nên không chốt được — cờ nghi vẫn phải được mang xuống.
    monkeypatch.setattr(
        classifier,
        "classify_image_local",
        lambda *a, **k: make_result(category_code="recyclable_paper", confidence=0.5, suspect_hazardous=True),
    )
    client = FakeVisionClient(results=[make_result(confidence=0.91)])
    monkeypatch.setattr(classifier, "get_vision_client", lambda tier="t1": client)
    monkeypatch.setattr(classifier, "get_tier_model", lambda tier: TIER_MODEL[tier])
    monkeypatch.setattr(classifier, "get_tier_provider", lambda tier: f"prov_{tier}")
    try:
        outcome = classifier.classify_waste(db_session, image_bytes=b"anh", image_phash="aabbccddeeff0011")
    finally:
        reset_settings_cache()

    assert outcome.tier == TIER_T2
    assert "đi thẳng T2" in outcome.escalation_reason
    assert client.calls == [("image", "M_T2")], "CLIP nghi cũng phải bỏ T1 mù, đi thẳng T2"
