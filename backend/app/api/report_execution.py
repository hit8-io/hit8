"""
Shared report execution logic for both streaming and batch modes.
"""
from __future__ import annotations

from typing import Any

import structlog

from app.api.graph_manager import get_graph
from app.constants import CONSTANTS
from app.flows.common import _get_first_available_llm_config
from app.flows.opgroeien.poc.db import _get_all_procedures_raw_sql

logger = structlog.get_logger(__name__)


def _resolve_report_model(user_model: str | None) -> str | None:
    """Return user-chosen model or first available so analyst, editor and consult share one model.
    
    Args:
        user_model: Optional user-specified model name.
        
    Returns:
        Model name to use, or None if no model available.
    """
    if user_model:
        return user_model
    cfg = _get_first_available_llm_config()
    return (cfg or {}).get("MODEL_NAME")


async def prepare_report_execution(
    thread_id: str,
    org: str,
    project: str,
    model: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], Any]:
    """Prepare report execution: fetch procedures, initialize state, get graph.
    
    Args:
        thread_id: Thread ID for the execution.
        org: Organization name.
        project: Project name.
        model: Optional model name to use.
        
    Returns:
        Tuple of (initial_state, config, graph):
        - initial_state: Initial state dictionary for the report graph
        - config: Configuration dictionary for graph execution
        - graph: Compiled graph instance
    """
    # Fetch all procedures from database
    try:
        procedures = _get_all_procedures_raw_sql()
        logger.info(
            "procedures_fetched_from_database",
            thread_id=thread_id,
            procedure_count=len(procedures),
        )
    except Exception as e:
        logger.exception(
            "failed_to_fetch_procedures",
            thread_id=thread_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise
    
    # Initialize state for new report - clear final_report from any previous run
    initial_state = {
        "raw_procedures": procedures,
        "final_report": "",  # Clear any previous final_report
    }
    
    # Resolve model
    resolved_model = _resolve_report_model(model)
    
    # Build config
    config = {
        "configurable": {
            "thread_id": thread_id
        },
        "recursion_limit": CONSTANTS.get("GRAPH_RECURSION_LIMIT", 50),  # Prevent infinite loops
    }
    if resolved_model:
        config["configurable"]["model_name"] = resolved_model
    
    # Get the report graph instance
    report_graph = get_graph(org, project, "report")
    
    return initial_state, config, report_graph


async def execute_report_graph(
    graph: Any,
    initial_state: dict[str, Any],
    config: dict[str, Any],
    thread_id: str,
    org: str,
    project: str,
) -> dict[str, Any]:
    """Execute report graph and return final state.
    
    Args:
        graph: Compiled graph instance.
        initial_state: Initial state dictionary.
        config: Configuration dictionary.
        thread_id: Thread ID for logging.
        org: Organization name for logging.
        project: Project name for logging.
        
    Returns:
        Final state dictionary from the graph execution.
    """
    logger.info(
        "report_job_execution_started",
        thread_id=thread_id,
        org=org,
        project=project,
    )
    
    try:
        # Execute the report graph
        await graph.ainvoke(initial_state, config)
        
        logger.info(
            "report_job_execution_completed",
            thread_id=thread_id,
            org=org,
            project=project,
        )
        
        # Get final state
        import asyncio
        snapshot = await asyncio.to_thread(graph.get_state, config)
        return snapshot.values if snapshot.values else {}
        
    except Exception as e:
        logger.exception(
            "report_job_execution_failed",
            thread_id=thread_id,
            org=org,
            project=project,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise
