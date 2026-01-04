"""Legacy runtime_graph module - maintained for backward compatibility.

This module re-exports from the new modular structure in `graph/`.
All new code should import directly from `graph.state`, `graph.nodes`, `graph.graph`.
"""

from __future__ import annotations

# Re-export for backward compatibility
from .graph.graph import graph, graph_local
from .graph.nodes import (
    act_node,
    finalize_node,
    frontend_tool_node,
    ingest_node,
    plan_node,
)
from .graph.state import GraphState

__all__ = [
    "GraphState",
    "act_node",
    "finalize_node",
    "frontend_tool_node",
    "graph",
    "graph_local",
    "ingest_node",
    "plan_node",
]
