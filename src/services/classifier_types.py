"""Kiểu dữ liệu dùng chung cho định tuyến phân loại rác.

Tách riêng để các module theo tầng (:mod:`src.services.classifier_stages`) và
lớp điều phối (:mod:`src.services.classifier`) cùng dùng một định nghĩa, không
ai định nghĩa lại.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.config import PROMPT_VERSION
from src.db.models import WasteCategory
from src.services.safety import HardBlockRule

TIER_T0_CACHE = "t0_cache"
TIER_T05_LOCAL = "t0_5_local"
TIER_T1 = "t1_mini"
TIER_T2 = "t2_full"

TIER_LABELS_VI: dict[str, str] = {
    TIER_T0_CACHE: "Đã biết câu trả lời",
    TIER_T05_LOCAL: "Nhận ra ngay trên máy",
    TIER_T1: "",
    TIER_T2: "Đã kiểm tra kỹ",
}


@dataclass
class NodeMetric:
    """Số liệu một bước xử lý — map thẳng vào bảng ``run_node_metrics``."""

    node: str
    status: str = "ok"
    duration_ms: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    image_tokens: int = 0
    cost_usd: float = 0.0
    cache_hits: int = 0
    llm_calls: int = 0
    retries: int = 0
    error_type: str = ""
    meta: dict = field(default_factory=dict)


@dataclass
class ClassifyOutcome:
    """Kết quả trọn vẹn của một lần phân loại."""

    item_name: str = ""
    category: WasteCategory | None = None
    confidence: float = 0.0
    min_confidence: float = 0.0
    confidence_level: str = "duoi_nguong"
    tier: str = ""
    model: str = ""
    provider: str = ""
    prompt_version: str = PROMPT_VERSION

    refused: bool = False
    refusal_reason: str = ""
    refusal_label_vi: str = ""
    refusal_headline_vi: str = ""
    guess_item_name: str = ""
    guess_category_code: str = ""

    hard_block: HardBlockRule | None = None
    escalation_reason: str = ""
    suspect_hazardous: bool = False
    safety_warning: str = ""
    items: list[dict] = field(default_factory=list)

    latency_ms: int = 0
    cost_usd: float = 0.0
    price_known: bool = True
    cache_source_id: int | None = None
    nodes: list[NodeMetric] = field(default_factory=list)

    @property
    def category_code(self) -> str:
        return self.category.code if self.category else ""
