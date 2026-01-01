"""
Graph management and initialization.
"""
from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import structlog

from app.agents.opgroeien.graph import create_agent_graph

if TYPE_CHECKING:
    from langgraph.graph import CompiledGraph

logger = structlog.get_logger(__name__)

# Lazy graph initialization - only create when needed
# This allows the app to start even if database connection fails initially
_graph: CompiledGraph | None = None
_graph_lock = threading.Lock()


def get_graph() -> CompiledGraph:
    """Get or create the graph instance (lazy initialization)."""
    global _graph
    if _graph is None:
        with _graph_lock:
            # Double-check pattern to avoid race conditions
            if _graph is None:
                try:
                    _graph = create_agent_graph()
                    logger.info("agent_graph_initialized_successfully")
                except Exception as e:
                    logger.error(
                        "graph_initialization_failed",
                        error=str(e),
                        error_type=type(e).__name__,
                    )
                    raise
    return _graph

