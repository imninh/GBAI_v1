"""LangGraph workflow for waste classification.

This is *the* classifier. Both the IoT capture endpoint and any future
web/PWA upload path go through it, so there is exactly one place where a waste
image becomes a label and exactly one place where safety rules apply
(spec §9, §26).

    vision  →  safety  →  END

The safety node runs unconditionally, including on the error path, so no route
through this graph can produce an outcome that skipped the safety rules.
"""

from langgraph.graph import END, StateGraph

from src.agents.nodes.classify_nodes import safety_node, vision_node
from src.agents.state import ClassifyState


def build_classify_graph():
    graph = StateGraph(ClassifyState)

    graph.add_node("vision", vision_node)
    graph.add_node("safety", safety_node)

    graph.set_entry_point("vision")
    graph.add_edge("vision", "safety")
    graph.add_edge("safety", END)

    return graph.compile()


classify_agent = build_classify_graph()
