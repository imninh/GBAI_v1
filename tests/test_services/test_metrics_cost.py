"""Kiểm việc phân biệt "$0 vì miễn phí thật" với "$0 vì chưa tra được giá".

Đây là chỗ dễ đọc nhầm nhất trên trang Vận hành: tầng T1 chạy model NVIDIA
không có bảng giá công bố nên ``cost_usd`` luôn bằng 0, và nếu UI in thẳng
"$0.0000" thì người đọc — kể cả người chấm — hiểu thành "tầng này miễn phí".
"Theo dõi chi phí" là yêu cầu bắt buộc của chương trình (PLO 5), nên báo $0
sai chỗ này tệ hơn là không báo gì.
"""

from __future__ import annotations

from datetime import UTC, datetime

from src.db.models import Classification
from src.services.classifier import TIER_T05_LOCAL, TIER_T1
from src.services.metrics import cost_metrics


def _ban_ghi(session, tier: str, model: str, cost: float = 0.0) -> None:
    session.add(
        Classification(
            tier=tier,
            model=model,
            cost_usd=cost,
            latency_ms=100,
            confidence=0.9,
            created_at=datetime.now(UTC),
        )
    )
    session.commit()


def _theo_tier(du_lieu: dict, tier: str) -> dict:
    return next(t for t in du_lieu["by_tier"] if t["tier"] == tier)


def test_model_khong_co_trong_bang_gia_thi_bao_chua_biet_gia(db_session):
    """Model NVIDIA không có giá công bố → ``price_known=False``, đừng in $0."""
    _ban_ghi(db_session, TIER_T1, "meta/llama-3.2-90b-vision-instruct")

    du_lieu = cost_metrics(db_session)

    assert _theo_tier(du_lieu, TIER_T1)["price_known"] is False


def test_model_co_trong_bang_gia_thi_bao_biet_gia(db_session):
    _ban_ghi(db_session, TIER_T1, "gpt-4o-mini", cost=0.0004)

    du_lieu = cost_metrics(db_session)

    assert _theo_tier(du_lieu, TIER_T1)["price_known"] is True


def test_tang_chay_tren_may_minh_la_mien_phi_that(db_session):
    """T0.5 chạy CLIP local — $0 ở đây là $0 thật, không phải "chưa biết"."""
    _ban_ghi(db_session, TIER_T05_LOCAL, "clip-vit-base-patch32 (onnx)")

    du_lieu = cost_metrics(db_session)

    assert _theo_tier(du_lieu, TIER_T05_LOCAL)["price_known"] is True


def test_mot_model_thieu_gia_lam_ca_tang_bi_danh_dau_chua_biet(db_session):
    """Trộn model biết giá và không biết giá thì tổng của tầng vẫn là số thiếu."""
    _ban_ghi(db_session, TIER_T1, "gpt-4o-mini", cost=0.0004)
    _ban_ghi(db_session, TIER_T1, "meta/llama-3.2-90b-vision-instruct")

    du_lieu = cost_metrics(db_session)

    assert _theo_tier(du_lieu, TIER_T1)["price_known"] is False
