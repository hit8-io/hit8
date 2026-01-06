"""
Graph management and initialization.

Provides thread-safe lazy initialization of the LangGraph agent graph.
The graph type is configurable via settings, allowing different agent
implementations to be used without code changes.
"""
from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Callable

import structlog

from app.config import settings

if TYPE_CHECKING:
    from langgraph.graph import CompiledGraph

logger = structlog.get_logger(__name__)

# Graph registry: maps graph type names to their creation functions
_GRAPH_REGISTRY: dict[str, Callable[[], CompiledGraph]] = {}


def register_graph(graph_type: str, create_func: Callable[[], CompiledGraph]) -> None:
    """Register a graph creation function for a given graph type.
    
    Args:
        graph_type: Name identifier for the graph type (e.g., "opgroeien", "simple")
        create_func: Function that creates and returns a CompiledGraph
    """
    _GRAPH_REGISTRY[graph_type] = create_func
    logger.debug("graph_registered", graph_type=graph_type)


def _get_graph_creator() -> Callable[[], CompiledGraph]:
    """Get the graph creation function based on configuration."""
    # Lazy import to ensure agents are registered
    # This avoids circular import issues
    if not _GRAPH_REGISTRY:
        import app.agents  # noqa: F401
    
    graph_type = settings.agent_graph_type
    
    if graph_type not in _GRAPH_REGISTRY:
        available = ", ".join(_GRAPH_REGISTRY.keys())
        raise ValueError(
            f"Unknown graph type '{graph_type}'. "
            f"Available types: {available if available else 'none registered'}"
        )
    
    return _GRAPH_REGISTRY[graph_type]


# Thread-safe lazy initialization
_graph: CompiledGraph | None = None
_graph_lock = threading.Lock()


def get_graph() -> CompiledGraph:
    """Get or create the compiled agent graph instance.
    
    Uses double-check locking to ensure thread-safe lazy initialization.
    The graph type is determined by the AGENT_GRAPH_TYPE setting.
    
    Returns:
        CompiledGraph: The compiled LangGraph agent graph.
        
    Raises:
        ValueError: If the configured graph type is not registered.
        Exception: Re-raises any exception from graph creation after logging.
    """
    global _graph
    
    # Fast path: return cached graph if already initialized
    if _graph is not None:
        return _graph
    
    # Slow path: initialize graph with thread-safe double-check locking
    with _graph_lock:
        if _graph is None:
            try:
                create_func = _get_graph_creator()
                graph_type = settings.agent_graph_type
                _graph = create_func()
                logger.info(
                    "agent_graph_initialized",
                    graph_type=graph_type,
                )
            except Exception as e:
                logger.error(
                    "graph_initialization_failed",
                    error=str(e),
                    error_type=type(e).__name__,
                    graph_type=settings.agent_graph_type,
                )
                raise
    
    return _graph

