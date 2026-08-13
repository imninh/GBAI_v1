"""Fix bug token của công cụ đo model (gói P44a) — không test nào gọi model/mạng thật.

Bug có sẵn từ P34: ``chay_mot_anh`` đọc ``outcome.tokens_in`` nhưng ``ClassifyOutcome``
không có field đó — token nằm trên từng ``NodeMetric`` trong ``outcome.nodes``. Chạy
``--dong-y`` model thật mới lộ (chủ dự án 13/08). Ba chỗ đáng ngờ: copy-paste
``tokens_in`` cho cả hai, gộp qua ``nodes`` hay đọc lại ``outcome.tokens_*``, và
``nodes`` rỗng có crash không.
"""

from __future__ import annotations

import inspect

from eval.so_sanh_model import _tong_token, chay_mot_anh
from src.services.classifier_types import ClassifyOutcome, NodeMetric


def test_tong_token_gop_qua_nodes() -> None:
    outcome = ClassifyOutcome()
    outcome.nodes = [
        NodeMetric(node="classify_waste", tokens_in=100, tokens_out=50),
        NodeMetric(node="classify_waste", tokens_in=3000, tokens_out=2000),
        NodeMetric(node="advise", tokens_in=600, tokens_out=90),
    ]

    assert _tong_token(outcome) == (3700, 2140)


def test_tong_token_khong_node() -> None:
    assert _tong_token(ClassifyOutcome()) == (0, 0)


def test_khong_con_outcome_tokens_in() -> None:
    """`chay_mot_anh` không được còn đọc thẳng `outcome.tokens_in`/`tokens_out`."""
    ma_nguon = inspect.getsource(chay_mot_anh)
    assert "outcome.tokens_in" not in ma_nguon, "Còn outcome.tokens_in — sẽ AttributeError khi chạy thật"
    assert "outcome.tokens_out" not in ma_nguon, "Còn outcome.tokens_out — sẽ AttributeError khi chạy thật"
