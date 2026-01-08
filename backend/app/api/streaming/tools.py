"""
Tool event processing functions.
"""
from __future__ import annotations

import threading
from typing import Any, Callable

import queue

import structlog

from app.api.constants import (
    EVENT_NODE_END,
    EVENT_NODE_START,
    EVENT_STATE_UPDATE,
    EVENT_TOOL_END,
    EVENT_TOOL_START,
)
from app.api.streaming.constants import QUEUE_EVENT
from app.api.streaming.llm import truncate_preview
from app.config import settings

logger = structlog.get_logger(__name__)

# Thread-safe cache for tool-to-node mappings per org/project
_tool_mappings: dict[tuple[str, str], dict[str, str]] = {}
_tool_mapping_lock = threading.Lock()


def _get_tool_to_node_map_creator(org: str, project: str) -> Callable[[], dict[str, str]] | None:
    """Get tool-to-node mapping function dynamically from graph module.
    
    Tries to import get_tool_to_node_map() or _get_tool_node_name_map() from
    app.flows.{org}.{project}.{flow}.graph
    
    Args:
        org: Organization name
        project: Project name
        
    Returns:
        Function that returns dict[str, str] mapping tool names to node names, or None if not found
    """
    flow = settings.FLOW
    
    # Build module path: app.flows.{org}.{project}.{flow}.graph
    module_path = f"app.flows.{org}.{project}.{flow}.graph"
    
    try:
        # Dynamically import the graph module
        import importlib
        graph_module = importlib.import_module(module_path)
        
        # Try to get get_tool_to_node_map (public) or _get_tool_node_name_map (private)
        mapping_func = getattr(graph_module, "get_tool_to_node_map", None)
        if mapping_func is None:
            mapping_func = getattr(graph_module, "_get_tool_node_name_map", None)
        
        if mapping_func is None:
            logger.debug(
                "tool_mapping_not_found",
                module_path=module_path,
                org=org,
                project=project,
                flow=flow,
            )
            return None
        
        return mapping_func
    except ImportError as e:
        logger.debug(
            "tool_mapping_module_import_failed",
            module_path=module_path,
            error=str(e),
            org=org,
            project=project,
            flow=flow,
        )
        return None
    except Exception as e:
        logger.warning(
            "tool_mapping_import_error",
            module_path=module_path,
            error=str(e),
            error_type=type(e).__name__,
            org=org,
            project=project,
            flow=flow,
        )
        return None


def get_tool_to_node_map(org: str, project: str) -> dict[str, str]:
    """Get mapping of tool names to node names for a specific org/project.
    
    Dynamically imports the mapping from the flow's graph module and caches it.
    Falls back to empty dict if mapping not available (tools will use tool_{tool_name}).
    
    Args:
        org: Organization name
        project: Project name
        
    Returns:
        Dictionary mapping tool names to their corresponding node names
    """
    cache_key = (org, project)
    
    # Fast path: return cached mapping if available
    if cache_key in _tool_mappings:
        return _tool_mappings[cache_key]
    
    # Slow path: dynamically import and cache with thread-safe double-check locking
    with _tool_mapping_lock:
        if cache_key not in _tool_mappings:
            mapping_func = _get_tool_to_node_map_creator(org, project)
            if mapping_func:
                try:
                    mapping = mapping_func()
                    if isinstance(mapping, dict):
                        _tool_mappings[cache_key] = mapping
                        logger.debug(
                            "tool_mapping_cached",
                            org=org,
                            project=project,
                            tool_count=len(mapping),
                        )
                    else:
                        logger.warning(
                            "tool_mapping_invalid_type",
                            org=org,
                            project=project,
                            mapping_type=type(mapping).__name__,
                        )
                        _tool_mappings[cache_key] = {}
                except Exception as e:
                    logger.warning(
                        "tool_mapping_execution_error",
                        org=org,
                        project=project,
                        error=str(e),
                        error_type=type(e).__name__,
                    )
                    _tool_mappings[cache_key] = {}
            else:
                # No mapping function found, use empty dict (fallback to tool_{tool_name})
                _tool_mappings[cache_key] = {}
                logger.debug(
                    "tool_mapping_not_available",
                    org=org,
                    project=project,
                )
    
    return _tool_mappings[cache_key]


def extract_tool_event_data(event: dict[str, Any], event_type: str) -> dict[str, Any] | None:
    """Extract tool invocation details from stream_events event.
    
    Args:
        event: Event dictionary from stream_events
        event_type: "on_tool_start" or "on_tool_end"
        
    Returns:
        Dictionary with tool event data or None if not applicable
    """
    import json
    
    data = event.get("data", {})
    if not isinstance(data, dict):
        return None
    
    # Extract tool name
    tool_name = data.get("name", "") or event.get("name", "") or "unknown"
    
    # Extract input (tool arguments)
    input_data = data.get("input", {})
    args_preview = ""
    if isinstance(input_data, dict):
        # Try to extract arguments
        args = input_data.get("input", input_data.get("args", input_data))
        if args:
            args_str = json.dumps(args) if not isinstance(args, str) else args
            args_preview = truncate_preview(args_str, 200)
        else:
            args_preview = truncate_preview(json.dumps(input_data), 200)
    elif input_data:
        args_str = json.dumps(input_data) if not isinstance(input_data, str) else str(input_data)
        args_preview = truncate_preview(args_str, 200)
    
    # Extract output (tool result, only for on_tool_end)
    result_preview = ""
    if event_type == "on_tool_end":
        output_data = data.get("output", {})
        if isinstance(output_data, dict):
            result_preview = truncate_preview(json.dumps(output_data), 500)
        elif output_data:
            result_str = json.dumps(output_data) if not isinstance(output_data, str) else str(output_data)
            result_preview = truncate_preview(result_str, 500)
    
    return {
        "tool_name": tool_name,
        "args_preview": args_preview,
        "result_preview": result_preview if event_type == "on_tool_end" else "",
    }


def process_tool_event(
    event: dict[str, Any],
    event_queue: queue.Queue,
    thread_id: str,
    visited_nodes: list[str],
    org: str,
    project: str,
) -> list[str]:
    """Process tool events from astream_events() to track individual tool nodes.
    
    Returns:
        Updated visited_nodes with individual tool nodes added
    """
    event_type = event.get("event", "")
    tool_data = extract_tool_event_data(event, event_type)
    
    if not tool_data:
        return visited_nodes
    
    tool_name = tool_data.get("tool_name", "unknown")
    
    # Map tool name to node name for graph view
    tool_to_node_map = get_tool_to_node_map(org, project)
    tool_node_name = tool_to_node_map.get(tool_name, f"tool_{tool_name}")
    
    # Track individual tool node in visited_nodes
    if tool_node_name not in visited_nodes:
        visited_nodes.append(tool_node_name)
        
        # Emit node_start for the tool
        event_queue.put((QUEUE_EVENT, {
            "type": EVENT_NODE_START,
            "node": tool_node_name,
            "thread_id": thread_id,
        }))
        
        # Send state update with tool node as active
        event_queue.put((QUEUE_EVENT, {
            "type": EVENT_STATE_UPDATE,
            "next": [tool_node_name],
            "message_count": 0,
            "thread_id": thread_id,
            "visited_nodes": visited_nodes.copy(),
        }))
    
    # Emit tool_start or tool_end event for frontend
    if event_type == "on_tool_start":
        event_queue.put((QUEUE_EVENT, {
            "type": EVENT_TOOL_START,
            "tool_name": tool_name,
            "args_preview": tool_data.get("args_preview", ""),
            "thread_id": thread_id,
        }))
    elif event_type == "on_tool_end":
        # Emit node_end for the tool
        event_queue.put((QUEUE_EVENT, {
            "type": EVENT_NODE_END,
            "node": tool_node_name,
            "thread_id": thread_id,
        }))
        
        event_queue.put((QUEUE_EVENT, {
            "type": EVENT_TOOL_END,
            "tool_name": tool_name,
            "args_preview": tool_data.get("args_preview", ""),
            "result_preview": tool_data.get("result_preview", ""),
            "thread_id": thread_id,
        }))
        
        # Send state update with individual tool nodes
        event_queue.put((QUEUE_EVENT, {
            "type": EVENT_STATE_UPDATE,
            "next": [],
            "message_count": 0,
            "thread_id": thread_id,
            "visited_nodes": visited_nodes.copy(),
        }))
    
    return visited_nodes
