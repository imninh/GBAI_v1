"""State của agent GreenBin.

State là thứ làm workflow này "có trạng thái" theo đúng nghĩa của chương trình:
nó đi qua ``classify → advise → schedule``, mỗi node đọc kết quả node trước và
bồi thêm phần của mình, và toàn bộ hành trình đó ghi lại được trong ``nodes``
để dựng màn Agent Run.
"""

from __future__ import annotations

from typing import Any, TypedDict

from src.models.schemas import ClassifyOutcome


class GreenBinState(TypedDict, total=False):
    """Schema state cho LangGraph. ``total=False`` nên mọi trường đều tuỳ chọn."""

    # --- Đầu vào ---
    session: Any  # sqlalchemy.orm.Session
    image_bytes: bytes | None
    image_phash: str
    text_query: str
    building_id: int | None
    user_id: int | None

    # --- Kết quả từng node ---
    outcome: Any  # src.services.classifier.ClassifyOutcome
    advice: Any  # src.services.rag.AdviceResult
    schedule_hint: dict[str, Any]

    # --- Vận hành ---
    nodes: list[Any]  # list[src.services.classifier.NodeMetric]
    error: str
    metadata: dict[str, Any]


# Giữ tên cũ để code mẫu của template không gãy khi còn tham chiếu tới.
AgentState = GreenBinState


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

