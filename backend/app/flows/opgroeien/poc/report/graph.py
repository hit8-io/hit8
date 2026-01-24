"""
Graph definition for the Long-Running Agent Reporting System.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from langgraph.graph import StateGraph, END
from langgraph.types import Send

from app.flows.opgroeien.poc.report.state import ReportState
from app.flows.opgroeien.poc.report.nodes import (
    splitter_node,
    analyst_node,
    batch_processor_node,
    batch_processor_noop_node,
    editor_node,
)
from app.api.checkpointer import get_checkpointer

logger = structlog.get_logger(__name__)

# Import constant from nodes module to avoid duplication
from app.flows.opgroeien.poc.report.nodes import SENDS_KEY

if TYPE_CHECKING:
    from langgraph.graph import CompiledGraph


def _extract_sends_from_output(output: dict[str, Any] | list[Send] | Any) -> list[Send] | str | None:
    """
    Extract Send objects from node output for conditional edge routing.
    
    Nodes can return:
    - A dict with SENDS_KEY containing a list of Send objects
    - A list of Send objects directly
    - Any other value (routes to default node)
    
    Args:
        output: Node output (dict, list, or other)
        
    Returns:
        - list[Send]: Send objects to route to (parallel execution)
        - str: Node name to route to
        - None: No routing (shouldn't happen, but type-safe)
    """
    if isinstance(output, dict) and SENDS_KEY in output:
        sends = output[SENDS_KEY]
        if isinstance(sends, list):
            return sends
        return None
    # Fallback: if output is already a list of Send objects, return as-is
    if isinstance(output, list):
        return output
    return None


def create_graph() -> CompiledGraph:
    """Create and compile the LangGraph report generation graph."""
    # Get checkpointer (initialized at application startup via FastAPI lifespan)
    checkpointer = get_checkpointer()
    
    # Create the graph
    workflow = StateGraph(ReportState)

    # Add Nodes
    workflow.add_node("splitter_node", splitter_node)
    
    # Analyst node: Retries are now handled inside the node with tenacity.
    # RetryPolicy is removed since all retry logic is centralized in the node.
    # The node returns failure status on errors/timeouts to allow graph to continue.
    workflow.add_node(
        "analyst_node",
        analyst_node,
    )
    
    workflow.add_node("batch_processor_node", batch_processor_node)
    workflow.add_node("batch_processor_noop_node", batch_processor_noop_node)
    workflow.add_node("editor_node", editor_node)

    # Set Entry
    workflow.set_entry_point("splitter_node")

    # Conditional Edge (Map) - Extract Send objects from splitter output
    # The splitter returns a dict with SENDS_KEY containing Send objects
    # We extract the Send objects for routing, and the dict (minus SENDS_KEY) is merged with state
    def route_splitter(output: dict[str, Any] | list[Send] | Any) -> list[Send] | str:
        sends = _extract_sends_from_output(output)
        if sends is not None:
            return sends
        # If no Send objects, route to editor (shouldn't happen, but safe fallback)
        return "editor_node"
    workflow.add_conditional_edges("splitter_node", route_splitter)

    # Standard Edge (Reduce)
    # LangGraph's reduce pattern waits for ALL Send() nodes to complete before following this edge.
    # The analyst_node now uses comprehensive flow control (semaphore, rate limiter, retries, timeout)
    # and returns failure status on errors/timeouts, allowing the graph to continue.
    workflow.add_edge("analyst_node", "batch_processor_node")

    # Conditional Edge for batch processor
    # Routes to analyst_node (sends) if more batches, batch_processor_noop_node when
    # waiting for more completions, editor_node if done, or retries failed chapters
    def route_batch_processor(output: dict[str, Any] | list[Send] | Any) -> list[Send] | str:
        # Handle partial failure recovery: retry failed chapters
        if isinstance(output, dict) and output.get("status") == "partial_failure":
            failed_chapter_ids = output.get("failed_chapter_ids", [])
            if not failed_chapter_ids:
                # No failed chapters to retry, route to editor
                return "editor_node"
            
            # Reconstruct cluster data for failed chapters from clusters_all
            # This allows us to retry only the failed chapters without re-running successful ones
            # CRITICAL: batch_processor_node must explicitly return clusters_all in output
            # LangGraph edges receive node output, not full state, so we rely on explicit return
            clusters_all = output.get("clusters_all")
            if not clusters_all or not isinstance(clusters_all, list) or len(clusters_all) == 0:
                logger.error(
                    "route_batch_processor_missing_clusters_all_in_output",
                    failed_chapter_ids=failed_chapter_ids,
                    clusters_all_present=clusters_all is not None,
                    clusters_all_type=type(clusters_all).__name__ if clusters_all is not None else "None",
                    clusters_all_length=len(clusters_all) if isinstance(clusters_all, list) else 0,
                    message="Cannot retry without cluster data - routing to editor to prevent infinite loop",
                )
                return "editor_node"  # Can't retry without cluster data - prevents infinite loop
            
            # Create a lookup map: file_id -> cluster
            cluster_map = {c.get("file_id"): c for c in clusters_all if c.get("file_id")}
            
            # Create Send objects for failed chapters only
            retry_sends = []
            for file_id in failed_chapter_ids:
                cluster = cluster_map.get(file_id)
                if cluster:
                    # Reset status to active for retry (will be updated when analyst starts)
                    retry_sends.append(
                        Send("analyst_node", {"procedures": cluster.get("procedures", []), "meta": cluster})
                    )
                else:
                    logger.warning(
                        "route_batch_processor_missing_cluster",
                        file_id=file_id,
                        available_file_ids=list(cluster_map.keys()),
                    )
            
            if retry_sends:
                logger.info(
                    "route_batch_processor_retrying_failed_chapters",
                    failed_count=len(failed_chapter_ids),
                    retry_count=len(retry_sends),
                    failed_ids=failed_chapter_ids,
                )
                return retry_sends
            # No valid clusters to retry, route to editor
            return "editor_node"
        
        # Handle normal routing (existing logic)
        sends = _extract_sends_from_output(output)
        if sends is not None:
            if sends:  # Non-empty list of Send objects
                return sends
            # Empty list: waiting for more completions, this branch ends via noop
            return "batch_processor_noop_node"
        # No more batches, route to editor
        return "editor_node"
    workflow.add_conditional_edges("batch_processor_node", route_batch_processor)

    workflow.add_edge("batch_processor_noop_node", END)
    workflow.add_edge("editor_node", END)

    # Compile with Checkpointer for persistence (Pause/Resume)
    return workflow.compile(checkpointer=checkpointer)
