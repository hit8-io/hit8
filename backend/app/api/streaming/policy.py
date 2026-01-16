"""
Flow-specific policies for event processing.

This module defines FlowPolicy dataclass for dependency injection of
flow-specific behavior (node filtering, preview extraction, metadata extraction).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class FlowPolicy:
    """Policy for flow-specific event processing behavior."""
    
    node_filter: Callable[[str], bool]
    """Filter function: returns True if node should be processed, False to skip."""
    
    extract_input_preview: Callable[[dict[str, Any]], str]
    """Extract input preview string from node input data."""
    
    extract_output_preview: Callable[[dict[str, Any]], str]
    """Extract output preview string from node output data."""
    
    extract_metadata: Callable[[dict[str, Any]], dict[str, Any]]
    """Extract flow-specific metadata from node input/output (e.g., file_id for report)."""


def create_chat_policy() -> FlowPolicy:
    """Create FlowPolicy for chat flow."""
    from app.api.streaming.llm import truncate_preview
    
    def node_filter(name: str) -> bool:
        """Filter out internal LangGraph nodes."""
        return name not in ("__start__", "__end__")
    
    def extract_input_preview(data: dict[str, Any]) -> str:
        """Extract input preview for chat nodes."""
        input_data = data.get("input", {})
        if isinstance(input_data, dict):
            return truncate_preview(str(input_data), 150)
        return truncate_preview(str(input_data), 150) if input_data else ""
    
    def extract_output_preview(data: dict[str, Any]) -> str:
        """Extract output preview for chat nodes."""
        output_data = data.get("output", {})
        if isinstance(output_data, dict):
            return truncate_preview(str(output_data), 150)
        return truncate_preview(str(output_data), 150) if output_data else ""
    
    def extract_metadata(data: dict[str, Any]) -> dict[str, Any]:
        """Extract metadata for chat nodes (none by default)."""
        return {}
    
    return FlowPolicy(
        node_filter=node_filter,
        extract_input_preview=extract_input_preview,
        extract_output_preview=extract_output_preview,
        extract_metadata=extract_metadata,
    )


def create_report_policy() -> FlowPolicy:
    """Create FlowPolicy for report flow."""
    from app.api.streaming.llm import truncate_preview
    
    def node_filter(name: str) -> bool:
        """Filter out internal LangGraph nodes."""
        return name not in ("__start__", "__end__")
    
    def extract_input_preview(data: dict[str, Any]) -> str:
        """Extract input preview for report nodes with flow-specific formatting."""
        input_data = data.get("input", {})
        if not isinstance(input_data, dict):
            return truncate_preview(str(input_data), 150) if input_data else ""
        
        node_name = data.get("node_name", "")
        
        # Report-specific previews
        if node_name == "analyst_node":
            if "meta" in input_data:
                meta = input_data.get("meta", {})
                topic = meta.get("topic_name", "")
                dept = meta.get("department_name", "")
                file_id = meta.get("file_id", "")
                proc_count = len(input_data.get("procedures", []))
                return f"FileID: {file_id}, Topic: {topic}, Dept: {dept}, Procedures: {proc_count}"
        elif node_name == "splitter_node":
            proc_count = len(input_data.get("raw_procedures", []))
            return f"Processing {proc_count} procedures"
        elif node_name == "batch_processor_node":
            pending = len(input_data.get("pending_clusters", []))
            return f"Pending clusters: {pending}"
        elif node_name == "editor_node":
            chapters = len(input_data.get("chapters", []))
            return f"Editing {chapters} chapters"
        
        return truncate_preview(str(input_data), 150)
    
    def extract_output_preview(data: dict[str, Any]) -> str:
        """Extract output preview for report nodes with flow-specific formatting."""
        output_data = data.get("output", {})
        if not isinstance(output_data, dict):
            return truncate_preview(str(output_data), 150) if output_data else ""
        
        node_name = data.get("node_name", "")
        
        # Report-specific previews
        if node_name == "analyst_node":
            chapters = output_data.get("chapters", [])
            if chapters and isinstance(chapters, list) and len(chapters) > 0:
                chapter_preview = truncate_preview(str(chapters[0]), 200)
                return f"Generated chapter: {chapter_preview}"
            return "Chapter generated"
        elif node_name == "splitter_node":
            clusters = len(output_data.get("pending_clusters", []))
            return f"Created clusters, {clusters} pending"
        elif node_name == "batch_processor_node":
            remaining = len(output_data.get("pending_clusters", []))
            return f"{remaining} clusters remaining"
        elif node_name == "editor_node":
            final_report = output_data.get("final_report")
            if final_report:
                report_preview = truncate_preview(str(final_report), 200)
                return f"Final report: {report_preview}"
            return "Report compiled"
        
        return truncate_preview(str(output_data), 150)
    
    def extract_metadata(data: dict[str, Any]) -> dict[str, Any]:
        """Extract metadata for report nodes (e.g., file_id for analyst_node)."""
        input_data = data.get("input", {})
        if not isinstance(input_data, dict):
            return {}
        
        node_name = data.get("node_name", "")
        metadata: dict[str, Any] = {}
        
        if node_name == "analyst_node" and "meta" in input_data:
            meta = input_data.get("meta", {})
            file_id = meta.get("file_id", "")
            if file_id:
                metadata["file_id"] = file_id
        
        return metadata
    
    return FlowPolicy(
        node_filter=node_filter,
        extract_input_preview=extract_input_preview,
        extract_output_preview=extract_output_preview,
        extract_metadata=extract_metadata,
    )


def get_flow_policy(flow: str) -> FlowPolicy:
    """Get FlowPolicy for the specified flow."""
    if flow == "report":
        return create_report_policy()
    else:
        return create_chat_policy()
