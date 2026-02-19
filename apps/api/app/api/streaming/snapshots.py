"""
Checkpoint snapshot generation and state extraction.

Handles checkpoint-authoritative state snapshots with throttling and async support.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from langgraph.graph import CompiledGraph  # type: ignore[import-untyped]

from app.api.streaming.nodes import extract_state_update

logger = structlog.get_logger(__name__)


async def get_checkpoint_state(
    graph: "CompiledGraph",
    config: dict[str, Any],
) -> Any | None:
    """
    Get checkpoint state using async method if available, otherwise sync in thread.
    
    Args:
        graph: Compiled LangGraph instance
        config: Graph configuration
        
    Returns:
        State snapshot or None if failed
    """
    try:
        # Try async method first (for AsyncPostgresSaver)
        if hasattr(graph, "aget_state"):
            return await graph.aget_state(config)
        else:
            # Fall back to sync method in thread
            return await asyncio.to_thread(graph.get_state, config)
    except Exception as e:
        logger.debug(
            "failed_to_get_checkpoint_state",
            error=str(e),
            error_type=type(e).__name__,
        )
        return None


def extract_snapshot_id(config: dict[str, Any], snapshot_seq: int) -> str:
    """
    Extract snapshot_id from config and sequence number.
    
    Args:
        config: Graph configuration
        snapshot_seq: Monotonic sequence number
        
    Returns:
        snapshot_id string (checkpoint_id:snapshot_seq or just snapshot_seq if no checkpoint_id)
    """
    checkpoint_id = None
    if isinstance(config, dict):
        configurable = config.get("configurable", {})
        if isinstance(configurable, dict):
            checkpoint_id = configurable.get("checkpoint_id")
    
    if checkpoint_id:
        return f"{checkpoint_id}:{snapshot_seq}"
    return str(snapshot_seq)


async def create_state_snapshot(
    graph: "CompiledGraph",
    config: dict[str, Any],
    thread_id: str,
    flow: str,
    visited_nodes: list[str],
    active_tasks: dict[str, dict[str, Any]],
    task_history: list[dict[str, Any]],
    snapshot_seq: int,
) -> dict[str, Any] | None:
    """
    Create a checkpoint-authoritative state snapshot.
    
    Args:
        graph: Compiled LangGraph instance
        config: Graph configuration
        thread_id: Thread identifier
        flow: Flow type ("chat" or "report")
        visited_nodes: List of visited node names
        active_tasks: Dict of active tasks keyed by run_id
        task_history: List of all tasks (for inspection)
        snapshot_seq: Monotonic sequence number
        
    Returns:
        State snapshot event dict or None if failed
    """
    state = await get_checkpoint_state(graph, config)
    if not state:
        return None
    
    # Extract state data
    state_data = _extract_state_snapshot_data(state, visited_nodes, flow)
    if not state_data:
        return None
    
    # Build snapshot
    snapshot_id = extract_snapshot_id(config, snapshot_seq)
    
    snapshot: dict[str, Any] = {
        "snapshot_id": snapshot_id,
        "next": state_data.get("next_nodes", []),
        "visited_nodes": state_data.get("visited_nodes", []),
    }
    
    # Add report state if available
    if "report_state" in state_data:
        snapshot["report_state"] = state_data["report_state"]
    
    # Add cluster_status for report flow
    if flow == "report":
        cluster_status = _extract_cluster_status(state_data, active_tasks, task_history)
        snapshot["cluster_status"] = cluster_status or {"active_cluster_ids": [], "completed_cluster_ids": []}
    
    # Add task_history for inspection
    if task_history:
        snapshot["task_history"] = task_history
    
    return snapshot


def _extract_state_snapshot_data(
    state: Any,
    visited_nodes: list[str],
    flow: str,
) -> dict[str, Any] | None:
    """Extract state data from checkpoint state."""
    final_visited_nodes = visited_nodes.copy()
    
    # Extract visited nodes from tasks
    if hasattr(state, "tasks") and state.tasks:
        for task in state.tasks:
            task_name = None
            if hasattr(task, "name"):
                task_name = task.name
            elif isinstance(task, dict) and "name" in task:
                task_name = task["name"]
            if task_name and task_name not in final_visited_nodes:
                final_visited_nodes.append(task_name)
    
    # Extract next nodes
    next_nodes = []
    if hasattr(state, "next") and state.next:
        next_nodes = list(state.next) if isinstance(state.next, (list, set, tuple)) else []
    
    # Extract message count
    message_count = 0
    if hasattr(state, "values") and state.values:
        if isinstance(state.values, dict) and "messages" in state.values:
            messages = state.values.get("messages", [])
            if isinstance(messages, list):
                message_count = len(messages)
    
    result: dict[str, Any] = {
        "visited_nodes": final_visited_nodes,
        "next_nodes": next_nodes,
        "message_count": message_count,
    }
    
    # Extract report-specific state
    if flow == "report" and hasattr(state, "values") and state.values:
        if isinstance(state.values, dict):
            report_state: dict[str, Any] = {}
            
            if "raw_procedures" in state.values:
                raw_procedures = state.values.get("raw_procedures", [])
                if raw_procedures is not None:
                    report_state["raw_procedures"] = raw_procedures
            
            if "pending_clusters" in state.values:
                report_state["pending_clusters"] = state.values.get("pending_clusters", [])
            
            if "chapters" in state.values:
                chapters = state.values.get("chapters", [])
                if isinstance(chapters, list):
                    report_state["chapters"] = chapters
            
            if "chapters_by_file_id" in state.values:
                chapters_by_file_id = state.values.get("chapters_by_file_id")
                if isinstance(chapters_by_file_id, dict):
                    report_state["chapters_by_file_id"] = chapters_by_file_id
            
            if "final_report" in state.values:
                final_report = state.values.get("final_report")
                if final_report is not None:
                    report_state["final_report"] = final_report
            
            # Include clusters_all if available (for UI display of all clusters)
            if "clusters_all" in state.values:
                clusters_all = state.values.get("clusters_all")
                if clusters_all is not None:
                    report_state["clusters_all"] = clusters_all
            
            # Extract cluster_status if available in state
            if "cluster_status" in state.values:
                cluster_status = state.values.get("cluster_status")
                if isinstance(cluster_status, dict):
                    report_state["cluster_status"] = cluster_status
            
            if report_state:
                result["report_state"] = report_state
    
    return result


def _extract_cluster_status(
    state_data: dict[str, Any],
    active_tasks: dict[str, dict[str, Any]],
    task_history: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """
    Extract cluster status from state data and active tasks.
    
    Args:
        state_data: Extracted state data
        active_tasks: Active tasks dict keyed by run_id
        task_history: All tasks for inspection
        
    Returns:
        Cluster status dict or None
    """
    cluster_status: dict[str, Any] = {
        "active_cluster_ids": [],
        "completed_cluster_ids": [],
    }
    
    # Extract active cluster IDs from active_tasks
    active_cluster_ids = set()
    for task_info in active_tasks.values():
        metadata = task_info.get("metadata", {})
        file_id = metadata.get("file_id")
        if file_id:
            active_cluster_ids.add(file_id)
    cluster_status["active_cluster_ids"] = list(active_cluster_ids)
    
    # Extract completed cluster IDs from state
    report_state = state_data.get("report_state", {})
    if "cluster_status" in report_state:
        # Use authoritative cluster_status from state if available
        state_cluster_status = report_state["cluster_status"]
        if isinstance(state_cluster_status, dict):
            completed_ids = [
                file_id
                for file_id, status_info in state_cluster_status.items()
                if isinstance(status_info, dict) and status_info.get("status") == "completed"
            ]
            cluster_status["completed_cluster_ids"] = completed_ids
    else:
        # Fallback: infer from chapters count vs pending_clusters
        chapters = report_state.get("chapters", [])
        pending = report_state.get("pending_clusters", [])
        if isinstance(chapters, list) and isinstance(pending, list):
            # If we have task_history, we can match completed clusters by file_id
            completed_ids = set()
            for task in task_history:
                if task.get("ended_at") and task.get("node_name") == "analyst_node":
                    metadata = task.get("metadata", {})
                    file_id = metadata.get("file_id")
                    if file_id:
                        completed_ids.add(file_id)
            cluster_status["completed_cluster_ids"] = list(completed_ids)
    
    return cluster_status
