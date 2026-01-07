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


def _get_graph_creator() -> Callable[[], CompiledGraph]:
    """Get the graph creation function dynamically from ORG/PROJECT/FLOW/graph.py.
    
    Derives the graph module path from constants:
    - Module: app.flows.{ORG}.{PROJECT}.{FLOW}.graph
    - Function: create_graph() or create_agent_graph() (tries both)
    
    Example: ORG="opgroeien", PROJECT="poc", FLOW="chat"
    -> app.flows.opgroeien.poc.chat.graph
    """
    from app import constants
    
    org = constants.CONSTANTS["ORG"]
    project = constants.CONSTANTS["PROJECT"]
    flow = settings.FLOW
    
    # Build module path: app.flows.{org}.{project}.{flow}.graph
    module_path = f"app.flows.{org}.{project}.{flow}.graph"
    
    try:
        # Dynamically import the graph module
        import importlib
        graph_module = importlib.import_module(module_path)
        
        # Try to get create_graph or create_agent_graph function
        create_func = getattr(graph_module, "create_graph", None)
        if create_func is None:
            create_func = getattr(graph_module, "create_agent_graph", None)
        
        if create_func is None:
            available_funcs = [name for name in dir(graph_module) if name.startswith("create")]
            raise ValueError(
                f"Graph module '{module_path}' does not export 'create_graph' or 'create_agent_graph'. "
                f"Available functions: {available_funcs}"
            )
        
        return create_func
    except ImportError as e:
        raise ValueError(
            f"Failed to import graph module '{module_path}': {e}. "
            f"Expected path: flows/{org}/{project}/{flow}/graph.py"
        ) from e


# Thread-safe lazy initialization
_graph: CompiledGraph | None = None
_graph_lock = threading.Lock()


def get_graph() -> CompiledGraph:
    """Get or create the compiled agent graph instance.
    
    Uses double-check locking to ensure thread-safe lazy initialization.
    The graph type is determined by the flow setting.
    
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
                from app import constants
                org = constants.CONSTANTS["ORG"]
                project = constants.CONSTANTS["PROJECT"]
                flow = settings.FLOW
                _graph = create_func()
                logger.info(
                    "agent_graph_initialized",
                    org=org,
                    project=project,
                    flow=flow,
                    graph_path=f"{org}/{project}/{flow}/graph.py",
                )
            except Exception as e:
                logger.error(
                    "graph_initialization_failed",
                    error=str(e),
                    error_type=type(e).__name__,
                    flow=settings.FLOW,
                )
                raise
    
    return _graph

