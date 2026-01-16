"""
Graph definition for the Long-Running Agent Reporting System.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from langgraph.graph import StateGraph, END

from app.flows.opgroeien.poc.report.state import ReportState
from app.flows.opgroeien.poc.report.nodes import (
    splitter_node,
    analyst_node,
    batch_processor_node,
    editor_node,
)
from app.api.checkpointer import get_checkpointer

if TYPE_CHECKING:
    from langgraph.graph import CompiledGraph


def create_graph() -> CompiledGraph:
    """Create and compile the LangGraph report generation graph."""
    # Get checkpointer (initialized at application startup via FastAPI lifespan)
    checkpointer = get_checkpointer()
    
    # Create the graph
    workflow = StateGraph(ReportState)

    # Add Nodes
    workflow.add_node("splitter_node", splitter_node)
    workflow.add_node("analyst_node", analyst_node)
    workflow.add_node("batch_processor_node", batch_processor_node)
    workflow.add_node("editor_node", editor_node)

    # Set Entry
    workflow.set_entry_point("splitter_node")

    # Conditional Edge (Map) - Extract Send objects from splitter output
    # The splitter returns a dict with "__sends__" key containing Send objects
    # We extract the Send objects for routing, and the dict (minus __sends__) is merged with state
    def route_splitter(output):
        if isinstance(output, dict) and "__sends__" in output:
            sends = output["__sends__"]
            # Remove __sends__ from output before it's merged with state
            # (LangGraph will merge the dict with state, but we handle routing here)
            return sends
        # Fallback: if output is already a list of Send objects, return as-is
        if isinstance(output, list):
            return output
        # If no Send objects, route to editor (shouldn't happen, but safe fallback)
        return "editor_node"
    workflow.add_conditional_edges("splitter_node", route_splitter)

    # Standard Edge (Reduce)
    # All analyst nodes point to batch_processor_node to check for more batches
    # The batch_processor_node will route to editor_node when all batches are done
    workflow.add_edge("analyst_node", "batch_processor_node")

    # Conditional Edge for batch processor
    # Routes to analyst_node if more batches, or editor_node if done
    def route_batch_processor(output):
        if isinstance(output, dict) and "__sends__" in output:
            # More batches to process - extract Send objects for routing
            return output["__sends__"]
        # No more batches, route to editor
        return "editor_node"
    workflow.add_conditional_edges("batch_processor_node", route_batch_processor)

    workflow.add_edge("editor_node", END)

    # Compile with Checkpointer for persistence (Pause/Resume)
    return workflow.compile(checkpointer=checkpointer)
