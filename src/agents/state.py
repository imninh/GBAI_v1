from __future__ import annotations

from typing import TypedDict

from src.models.schemas import ClassifyOutcome


class AgentState(TypedDict, total=False):
    """State schema cho LangGraph agent.

    Mỗi node đọc và ghi vào state này.
    total=False cho phép tất cả fields là optional.
    """

    query: str
    context: str
    analysis: str
    response: str
    error: str
    metadata: dict


class ClassifyState(TypedDict, total=False):
    """State schema cho waste-classification graph.

    `image_b64` luôn là ảnh ĐÃ qua privacy pipeline (src.services.image_privacy),
    không bao giờ là ảnh gốc từ thiết bị.
    """

    image_b64: str
    phash: str
    source: str  # "iot" | "web"
    label: str
    confidence: float
    error: str
    outcome: ClassifyOutcome
