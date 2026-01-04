"""LangGraph builder and compilation."""

from __future__ import annotations

import os
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.constants import END, START
from langgraph.graph import StateGraph

from .nodes import act_node, finalize_node, frontend_tool_node, ingest_node, plan_node
from .state import GraphState


def _get_checkpointer():
    """Get checkpointer based on environment variable.
    
    If V2_CHECKPOINT_DIR is set, use SQLite checkpointer (shared between Studio and FastAPI).
    Otherwise, use in-memory checkpointer (default behavior).
    """
    checkpoint_dir = os.getenv("V2_CHECKPOINT_DIR", "").strip()
    if checkpoint_dir:
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver
            
            checkpoint_path = Path(checkpoint_dir)
            checkpoint_path.mkdir(parents=True, exist_ok=True)
            db_path = checkpoint_path / "checkpoints.db"
            
            return SqliteSaver.from_conn_string(str(db_path))
        except ImportError:
            # Fallback to in-memory if SQLite not available
            return InMemorySaver()
        except Exception:
            # Fallback to in-memory on any error
            return InMemorySaver()
    return InMemorySaver()


_checkpointer = _get_checkpointer()

_builder = StateGraph(GraphState)
_builder.add_node("ingest_node", ingest_node)
_builder.add_node("plan_node", plan_node)
_builder.add_node("act_node", act_node)
_builder.add_node("finalize_node", finalize_node)
_builder.add_node("frontend_tool_node", frontend_tool_node)
_builder.add_conditional_edges(
    "act_node",
    lambda state: state["next_step_kind"],
    {
        "tool": "frontend_tool_node",
        "final": "finalize_node",
    },
)
_builder.add_edge(START, "ingest_node")
_builder.add_edge("ingest_node", "plan_node")
_builder.add_edge("plan_node", "act_node")
_builder.add_edge("frontend_tool_node", "act_node")
_builder.add_edge("finalize_node", END)

# `graph` is the entrypoint used by LangGraph Studio (langgraph dev).
# Studio manages persistence automatically, so we must NOT attach a custom checkpointer here.
# Studio will use its own in-memory or SQLite persistence (managed by langgraph dev).
graph = _builder.compile()

# `graph_local` is used by FastAPI server.
# Uses SQLite checkpointer if V2_CHECKPOINT_DIR is set (for persistence and potential sharing),
# otherwise uses in-memory checkpointer (default behavior).
graph_local = _builder.compile(checkpointer=_checkpointer)
