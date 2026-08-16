"""Graph LangGraph của GreenBin: ``classify → advise → schedule``.

```
                 ┌─ đã từ chối trả lời ──► skip_advise ──────────────┐
classify_waste ──┤                                                    ├──► kết thúc
                 └─ trả lời được ──► advise ──┬─ cồng kềnh ──► schedule_pickup
                                              └─ còn lại ────► skip_schedule
```

Hai nhánh "skip" tồn tại có chủ đích chứ không phải cho đẹp sơ đồ: chúng vẫn
sinh bản ghi node với ``status="skipped"`` kèm lý do, nên trên màn Agent Run
người xem thấy được **đường đã đi và đường không đi**, đúng yêu cầu trace.
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from src.agents.nodes.classify_node import (
    advise_node,
    classify_node,
    schedule_node,
    skip_advise_node,
    skip_schedule_node,
)
from src.agents.state import GreenBinState


def _sau_khi_phan_loai(state: GreenBinState) -> str:
    """Từ chối trả lời thì không đi tra quy định nữa."""
    outcome = state.get("outcome")
    if outcome is None or outcome.refused:
        return "skip_advise"
    return "advise"


def _sau_khi_tu_van(state: GreenBinState) -> str:
    """Chỉ đồ cồng kềnh mới cần gợi ý lịch thu gom."""
    outcome = state.get("outcome")
    if outcome is not None and outcome.category is not None and outcome.category.code == "bulky":
        return "schedule_pickup"
    return "skip_schedule"


def build_graph():
    """Dựng và biên dịch graph."""
    graph = StateGraph(GreenBinState)

    graph.add_node("classify_waste", classify_node)
    graph.add_node("advise", advise_node)
    graph.add_node("skip_advise", skip_advise_node)
    graph.add_node("schedule_pickup", schedule_node)
    graph.add_node("skip_schedule", skip_schedule_node)

    graph.set_entry_point("classify_waste")
    graph.add_conditional_edges(
        "classify_waste",
        _sau_khi_phan_loai,
        {"advise": "advise", "skip_advise": "skip_advise"},
    )
    graph.add_conditional_edges(
        "advise",
        _sau_khi_tu_van,
        {"schedule_pickup": "schedule_pickup", "skip_schedule": "skip_schedule"},
    )
    graph.add_edge("skip_advise", END)
    graph.add_edge("schedule_pickup", END)
    graph.add_edge("skip_schedule", END)

    return graph.compile()


agent = build_graph()


# Mô tả graph cho UI vẽ sơ đồ (spec 4.15) — để một chỗ đổi là cả backend lẫn
# frontend cùng đổi theo.
GRAPH_SHAPE: dict[str, list[dict[str, str]]] = {
    "nodes": [
        {"id": "classify_waste", "label": "Phân loại rác"},
        {"id": "advise", "label": "Tra quy định (RAG)"},
        {"id": "skip_advise", "label": "Bỏ qua — đã từ chối trả lời"},
        {"id": "schedule_pickup", "label": "Gợi ý lịch thu gom"},
        {"id": "skip_schedule", "label": "Bỏ qua — không phải đồ cồng kềnh"},
    ],
    "edges": [
        {"from": "classify_waste", "to": "advise", "label": "trả lời được"},
        {"from": "classify_waste", "to": "skip_advise", "label": "từ chối trả lời"},
        {"from": "advise", "to": "schedule_pickup", "label": "đồ cồng kềnh"},
        {"from": "advise", "to": "skip_schedule", "label": "còn lại"},
    ],
}
