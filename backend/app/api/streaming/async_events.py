"""
Pure async event processing for LangGraph streaming.

This module processes astream_events() directly in the FastAPI event loop,
eliminating the need for background threads and event loop synchronization.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, AsyncIterator

import structlog

from app.api.constants import (
    EVENT_CONTENT_CHUNK,
    EVENT_GRAPH_END,
    EVENT_GRAPH_START,
    EVENT_NODE_END,
    EVENT_NODE_START,
    EVENT_STATE_SNAPSHOT,
    EVENT_STATE_UPDATE,
    EVENT_TOOL_END,
    EVENT_TOOL_START,
)

if TYPE_CHECKING:
    from langgraph.graph import CompiledGraph  # type: ignore[import-untyped]
from app.api.streaming.envelope import EVENT_TYPE_MAPPING, create_event_envelope
from app.api.streaming.llm import (
    extract_llm_end_event,
    extract_llm_start_event,
    process_chat_model_stream_event,
)
from app.api.streaming.nodes import extract_state_update
from app.api.streaming.policy import FlowPolicy, get_flow_policy
from app.api.streaming.snapshots import create_state_snapshot, extract_snapshot_id
from app.api.streaming.tools import extract_tool_event_data, get_tool_to_node_map
from app.api.streaming.llm import truncate_preview

logger = structlog.get_logger(__name__)

# Import cancellation registry for report flow
try:
    from app.api.routes.report import _cancelled_threads
except ImportError:
    # Fallback if import fails (shouldn't happen in normal operation)
    _cancelled_threads: dict[str, bool] = {}

logger = structlog.get_logger(__name__)

# Constants
SNAPSHOT_THROTTLE_INTERVAL = 12.0  # seconds - emit snapshot every 12s during long tasks
LONG_RUNNING_TASK_THRESHOLD = 20.0  # seconds - task is considered long-running after 20s
REPORT_KEEPALIVE_INTERVAL = 30.0  # seconds - send keepalive snapshot every 30s for report flows (even with no active tasks)
DEFAULT_PREVIEW_LENGTH = 150  # characters for default preview truncation
CHAPTER_PREVIEW_LENGTH = 200  # characters for chapter preview truncation
TOOL_RESULT_PREVIEW_LENGTH = 500  # characters for tool result preview truncation


@dataclass
class NodeEventResult:
    """Result from processing a node event."""
    events: list[dict[str, Any]]
    current_node: str | None
    visited_nodes: list[str]
    active_tasks: dict[str, dict[str, Any]]
    task_history: list[dict[str, Any]]
    active_cluster_ids: set[str]
    should_snapshot: bool


def _extract_run_id(event: dict[str, Any], node_name: str = "") -> str:
    """
    Extract run_id from LangGraph event.
    
    Each Send() instance in LangGraph has its own run_id. This function extracts it
    from the event structure, with fallbacks for sequential nodes that may not have
    explicit run_ids.
    
    Args:
        event: LangGraph event dictionary
        node_name: Optional node name for fallback run_id generation
        
    Returns:
        run_id string (may be constructed from node_name if event doesn't have one)
    """
    # Try to get run_id from event.run.id
    event_run = event.get("run", {})
    if isinstance(event_run, dict):
        event_run_id = event_run.get("id", "")
        if event_run_id:
            # If we have both node_name and run_id, combine them for uniqueness
            if node_name:
                return f"{node_name}_{event_run_id}"
            return event_run_id
    
    # Last resort: use node_name as run_id for sequential nodes
    if node_name:
        return node_name
    
    return ""


def _create_envelope_event(
    event_type: str,
    thread_id: str,
    flow: str,
    event_seq: int,
    run_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> str:
    """
    Create and format an SSE envelope event.
    
    Args:
        event_type: Event type constant (e.g., EVENT_NODE_START)
        thread_id: Thread identifier
        flow: Flow type ("chat" or "report")
        event_seq: Monotonic sequence number
        run_id: Optional run_id for parallel task tracking
        payload: Optional event-specific payload
        
    Returns:
        SSE-formatted string ready to yield
    """
    envelope = create_event_envelope(
        event_type=event_type,
        thread_id=thread_id,
        flow=flow,
        seq=event_seq,
        run_id=run_id,
        payload=payload,
    )
    return f"data: {json.dumps(envelope)}\n\n"


def _should_emit_throttled_snapshot(
    current_time: float,
    last_snapshot_time: float,
    active_tasks: dict[str, dict[str, Any]],
) -> bool:
    """
    Determine if a throttled snapshot should be emitted.
    
    Throttled snapshots are emitted during long-running tasks to provide progress
    updates and prevent stream timeouts. They are emitted every SNAPSHOT_THROTTLE_INTERVAL
    seconds when there are active tasks that have been running longer than
    LONG_RUNNING_TASK_THRESHOLD seconds.
    
    Args:
        current_time: Current timestamp
        last_snapshot_time: Timestamp of last snapshot
        active_tasks: Dict of active tasks keyed by run_id
        
    Returns:
        True if throttled snapshot should be emitted
    """
    if current_time - last_snapshot_time < SNAPSHOT_THROTTLE_INTERVAL:
        return False
    
    # Check if there are active long-running tasks
    long_running_tasks = [
        task for task in active_tasks.values()
        if current_time - task.get("started_at", 0) > LONG_RUNNING_TASK_THRESHOLD
    ]
    return len(long_running_tasks) > 0


async def _emit_throttled_snapshot(
    graph: "CompiledGraph",
    config: dict[str, Any],
    thread_id: str,
    flow: str,
    visited_nodes: list[str],
    active_tasks: dict[str, dict[str, Any]],
    task_history: list[dict[str, Any]],
    snapshot_seq: int,
    event_seq: int,
) -> tuple[int, int, dict[str, Any] | None]:
    """
    Emit a throttled state snapshot for long-running tasks.
    
    Args:
        graph: Compiled LangGraph instance
        config: Graph configuration
        thread_id: Thread identifier
        flow: Flow type
        visited_nodes: List of visited nodes
        active_tasks: Active tasks dict
        task_history: Task history list
        snapshot_seq: Current snapshot sequence number
        event_seq: Current event sequence number
        
    Returns:
        Tuple of (updated_snapshot_seq, updated_event_seq, snapshot_dict or None)
    """
    snapshot_seq += 1
    event_seq += 1
    snapshot = await create_state_snapshot(
        graph, config, thread_id, flow, visited_nodes,
        active_tasks, task_history, snapshot_seq
    )
    return snapshot_seq, event_seq, snapshot


@dataclass
class StreamState:
    """State tracked during event stream processing."""
    event_seq: int
    snapshot_seq: int
    last_snapshot_time: float
    accumulated_content: str
    last_ai_message_content: str
    visited_nodes: list[str]
    current_node: str | None
    active_tasks: dict[str, dict[str, Any]]
    task_history: list[dict[str, Any]]
    active_cluster_ids: set[str]
    first_token_recorded: bool


def _initialize_stream_state(
    initial_state: dict[str, Any],
    config: dict[str, Any],
    thread_id: str,
    flow: str,
) -> tuple[StreamState, FlowPolicy, int, int]:
    """
    Initialize stream state and send initial events.
    
    Args:
        initial_state: Initial agent state
        config: Graph configuration
        thread_id: Thread identifier
        flow: Flow type
        
    Returns:
        Tuple of (StreamState, FlowPolicy, event_seq, snapshot_seq)
    """
    import time
    
    # Initialize state
    stream_state = StreamState(
        event_seq=0,
        snapshot_seq=0,
        last_snapshot_time=time.time(),
        accumulated_content="",
        last_ai_message_content="",
        visited_nodes=[],
        current_node=None,
        active_tasks={},
        task_history=[],
        active_cluster_ids=set(),
        first_token_recorded=False,
    )
    
    flow_policy = get_flow_policy(flow)
    
    # Send graph_start event
    stream_state.event_seq += 1
    # Note: graph_start is yielded by caller after initialization
    
    # Send initial state snapshot for report flow
    if flow == "report" and "raw_procedures" in initial_state:
        stream_state.snapshot_seq += 1
        stream_state.event_seq += 1
        # Note: initial snapshot is yielded by caller after initialization
    
    return stream_state, flow_policy, stream_state.event_seq, stream_state.snapshot_seq


async def _process_event_loop(
    graph: "CompiledGraph",
    initial_state: dict[str, Any],
    config: dict[str, Any],
    thread_id: str,
    org: str,
    project: str,
    flow: str,
    flow_policy: FlowPolicy,
    stream_state: StreamState,
    accumulated_content_ref: dict[str, str] | None,
) -> AsyncIterator[str]:
    """
    Process the main event loop from astream_events.
    
    This function handles the core event processing loop, including:
    - Throttled snapshot emission for long-running tasks
    - Event type routing (content chunks, LLM, tool, node events)
    - State tracking updates
    - Error handling per event
    
    Args:
        graph: Compiled LangGraph instance
        initial_state: Initial agent state
        config: Graph configuration
        thread_id: Thread identifier
        org: Organization name
        project: Project name
        flow: Flow type
        flow_policy: FlowPolicy instance
        stream_state: StreamState instance (mutated)
        accumulated_content_ref: Optional mutable dict for accumulated content
        
    Yields:
        SSE-formatted strings
    """
    import time
    
    try:
        # Stream events directly from graph - runs in main event loop
        async for event in graph.astream_events(initial_state, config=config, version="v2"):
            if not isinstance(event, dict):
                continue
            
            event_type = event.get("event", "")
            
            # Simple cancellation check: if cancelled, stop processing new node starts
            # Current nodes finish, but no new nodes start (no polling)
            if event_type == "on_chain_start" and flow == "report":
                if _cancelled_threads.get(thread_id, False):
                    logger.info(
                        "report_cancelled_stopping_new_nodes",
                        thread_id=thread_id,
                        event_name=event.get("name", ""),
                    )
                    break  # Current nodes finish, but no new nodes start
            
            # Extract run_id from event (for parallel task tracking)
            run_id = _extract_run_id(event)
            
            # Check if we need to emit a throttled snapshot (for long tasks)
            # For report flow, also send keepalive events during long waits (e.g., retries)
            current_time = time.time()
            time_since_last_snapshot = current_time - stream_state.last_snapshot_time
            
            # For report flow: send keepalive/snapshot every REPORT_KEEPALIVE_INTERVAL seconds even if no active tasks
            # This prevents frontend timeout during long retry periods and rate limiting delays
            # With 10-minute frontend timeout, 30s keepalive provides 20x safety margin
            if flow == "report" and time_since_last_snapshot >= REPORT_KEEPALIVE_INTERVAL:
                # Send a snapshot to keep the stream alive, even if no active tasks
                stream_state.snapshot_seq, stream_state.event_seq, snapshot = await _emit_throttled_snapshot(
                    graph, config, thread_id, flow, stream_state.visited_nodes,
                    stream_state.active_tasks, stream_state.task_history,
                    stream_state.snapshot_seq, stream_state.event_seq
                )
                if snapshot:
                    yield _create_envelope_event(
                        event_type=EVENT_STATE_SNAPSHOT,
                        thread_id=thread_id,
                        flow=flow,
                        event_seq=stream_state.event_seq,
                        payload=snapshot,
                    )
                    stream_state.last_snapshot_time = current_time
            elif _should_emit_throttled_snapshot(current_time, stream_state.last_snapshot_time, stream_state.active_tasks):
                # Normal throttled snapshot logic (for active tasks)
                stream_state.snapshot_seq, stream_state.event_seq, snapshot = await _emit_throttled_snapshot(
                    graph, config, thread_id, flow, stream_state.visited_nodes,
                    stream_state.active_tasks, stream_state.task_history,
                    stream_state.snapshot_seq, stream_state.event_seq
                )
                if snapshot:
                    yield _create_envelope_event(
                        event_type=EVENT_STATE_SNAPSHOT,
                        thread_id=thread_id,
                        flow=flow,
                        event_seq=stream_state.event_seq,
                        payload=snapshot,
                    )
                    stream_state.last_snapshot_time = current_time
            
            # Process event using dispatcher pattern with error handling
            try:
                if event_type == "on_chat_model_stream":
                    # Track first token arrival for TTFT calculation
                    if not stream_state.first_token_recorded and not stream_state.accumulated_content:
                        stream_state.first_token_recorded = True
                        try:
                            from app.api.observability import record_first_token
                            event_run_id = _extract_run_id(event)
                            record_first_token(thread_id, run_id=event_run_id if event_run_id else None)
                        except Exception:
                            # Don't fail if observability is not available
                            pass
                    
                    # Process content chunk
                    chunk_data = process_chat_model_stream_event(event, thread_id, stream_state.accumulated_content)
                    if chunk_data:
                        incremental_chunk, new_accumulated = chunk_data
                        stream_state.accumulated_content = new_accumulated
                        stream_state.last_ai_message_content = new_accumulated
                        
                        # Update accumulated content reference if provided
                        if accumulated_content_ref is not None:
                            accumulated_content_ref["content"] = new_accumulated
                        
                        # Yield content chunk event with envelope
                        stream_state.event_seq += 1
                        yield _create_envelope_event(
                            event_type=EVENT_CONTENT_CHUNK,
                            thread_id=thread_id,
                            flow=flow,
                            event_seq=stream_state.event_seq,
                            run_id=run_id if run_id else None,
                            payload={
                                "content": incremental_chunk,
                                "accumulated": new_accumulated,
                            },
                        )
                
                # Handle LLM events
                elif event_type in ("on_llm_start", "on_chat_model_start"):
                    llm_start_data = extract_llm_start_event(event, thread_id)
                    if llm_start_data:
                        stream_state.event_seq += 1
                        yield _create_envelope_event(
                            event_type=llm_start_data["type"],
                            thread_id=thread_id,
                            flow=flow,
                            event_seq=stream_state.event_seq,
                            run_id=run_id if run_id else None,
                            payload={
                                "model": llm_start_data.get("model", ""),
                                "input_preview": llm_start_data.get("input_preview", ""),
                                "call_id": llm_start_data.get("call_id"),
                            },
                        )
                
                elif event_type in ("on_llm_end", "on_chat_model_end"):
                    llm_end_data = extract_llm_end_event(event, thread_id)
                    if llm_end_data:
                        stream_state.event_seq += 1
                        yield _create_envelope_event(
                            event_type=llm_end_data["type"],
                            thread_id=thread_id,
                            flow=flow,
                            event_seq=stream_state.event_seq,
                            run_id=run_id if run_id else None,
                            payload={
                                "model": llm_end_data.get("model", ""),
                                "input_preview": llm_end_data.get("input_preview", ""),
                                "output_preview": llm_end_data.get("output_preview", ""),
                                "token_usage": llm_end_data.get("token_usage"),
                                "execution_metrics": llm_end_data.get("execution_metrics"),
                            },
                        )
                
                # Handle tool events
                elif event_type in ("on_tool_start", "on_tool_end"):
                    tool_events = _process_tool_event_async(
                        event, event_type, thread_id, stream_state.visited_nodes, org, project, flow, run_id
                    )
                    for tool_event in tool_events:
                        stream_state.event_seq += 1
                        yield _create_envelope_event(
                            event_type=tool_event["type"],
                            thread_id=thread_id,
                            flow=flow,
                            event_seq=stream_state.event_seq,
                            run_id=tool_event.get("run_id") or run_id if run_id else None,
                            payload={
                                k: v for k, v in tool_event.items()
                                if k not in ("type", "thread_id", "run_id")
                            },
                        )
                
                # Handle node events (chain start/end)
                elif event_type in ("on_chain_start", "on_chain_end"):
                    node_results = _process_node_event_async(
                        event, event_type, thread_id, stream_state.current_node,
                        stream_state.visited_nodes, flow,
                        stream_state.active_tasks, stream_state.task_history,
                        stream_state.active_cluster_ids, flow_policy, run_id
                    )
                    stream_state.current_node = node_results.current_node
                    stream_state.visited_nodes = node_results.visited_nodes
                    stream_state.active_tasks = node_results.active_tasks
                    stream_state.task_history = node_results.task_history
                    stream_state.active_cluster_ids = node_results.active_cluster_ids
                    
                    # Yield node events with envelopes
                    for node_event in node_results.events:
                        stream_state.event_seq += 1
                        event_run_id = node_event.get("run_id") or run_id if run_id else None
                        yield _create_envelope_event(
                            event_type=node_event["type"],
                            thread_id=thread_id,
                            flow=flow,
                            event_seq=stream_state.event_seq,
                            run_id=event_run_id,
                            payload={
                                k: v for k, v in node_event.items()
                                if k not in ("type", "thread_id")
                            },
                        )
                    
                    # Emit checkpoint snapshot after node_start for analyst_node in report flow
                    # This ensures the frontend gets active_cluster_ids immediately when analyst_node starts,
                    # not just after it completes. This provides real-time feedback during long-running nodes.
                    # Check node_name from the event, not current_node, because parallel nodes don't update current_node
                    node_name_from_event = event.get("name", "")
                    if event_type == "on_chain_start" and flow == "report" and node_name_from_event == "analyst_node":
                        stream_state.snapshot_seq += 1
                        stream_state.event_seq += 1
                        snapshot = await create_state_snapshot(
                            graph, config, thread_id, flow, stream_state.visited_nodes,
                            stream_state.active_tasks, stream_state.task_history, stream_state.snapshot_seq
                        )
                        if snapshot:
                            yield _create_envelope_event(
                                event_type=EVENT_STATE_SNAPSHOT,
                                thread_id=thread_id,
                                flow=flow,
                                event_seq=stream_state.event_seq,
                                payload=snapshot,
                            )
                            stream_state.last_snapshot_time = time.time()
                    
                    # Emit checkpoint snapshot after node_end
                    # Snapshots are emitted after every node_end to provide checkpoint-authoritative
                    # state updates. This ensures the frontend always has the latest state from
                    # the checkpointer, not just from event outputs.
                    if event_type == "on_chain_end" and node_results.should_snapshot:
                        stream_state.snapshot_seq += 1
                        stream_state.event_seq += 1
                        snapshot = await create_state_snapshot(
                            graph, config, thread_id, flow, stream_state.visited_nodes,
                            stream_state.active_tasks, stream_state.task_history, stream_state.snapshot_seq
                        )
                        if snapshot:
                            yield _create_envelope_event(
                                event_type=EVENT_STATE_SNAPSHOT,
                                thread_id=thread_id,
                                flow=flow,
                                event_seq=stream_state.event_seq,
                                payload=snapshot,
                            )
                            stream_state.last_snapshot_time = time.time()
            except Exception as e:
                # Log error but continue processing (don't break entire stream)
                logger.warning(
                    "event_processing_error",
                    event_type=event_type,
                    error=str(e),
                    error_type=type(e).__name__,
                    thread_id=thread_id,
                    exc_info=True,
                )
                # Continue to next event
    except Exception as e:
        logger.exception(
            "async_stream_error",
            error=str(e),
            error_type=type(e).__name__,
            thread_id=thread_id,
            exc_info=True,
        )
        # Error event will be handled by caller
        raise


async def _finalize_stream(
    graph: "CompiledGraph",
    config: dict[str, Any],
    thread_id: str,
    flow: str,
    stream_state: StreamState,
) -> AsyncIterator[str]:
    """
    Send final state snapshot and clean up.
    
    Args:
        graph: Compiled LangGraph instance
        config: Graph configuration
        thread_id: Thread identifier
        flow: Flow type
        stream_state: StreamState instance
        
    Yields:
        Final SSE-formatted strings
    """
    # End any remaining active tasks
    # This ensures that nodes like splitter_node and batch_processor_node
    # that may have missed their on_chain_end events are properly marked as completed
    remaining_tasks = list(stream_state.active_tasks.items())
    if remaining_tasks:
        logger.debug(
            "finalizing_remaining_active_tasks",
            thread_id=thread_id,
            flow=flow,
            remaining_tasks_count=len(remaining_tasks),
            node_names=[task_info.get("node_name") for _, task_info in remaining_tasks],
        )
    
    for run_id, task_info in remaining_tasks:
        node_name = task_info.get("node_name")
        if node_name:
            # Emit node_end for this task
            stream_state.event_seq += 1
            yield _create_envelope_event(
                event_type=EVENT_NODE_END,
                thread_id=thread_id,
                flow=flow,
                event_seq=stream_state.event_seq,
                run_id=run_id,
                payload={
                    "node": node_name,
                    "output_preview": task_info.get("output_preview"),
                },
            )
            # Move to task_history
            task_info["ended_at"] = time.time()
            stream_state.task_history.append(task_info.copy())
            # Update visited nodes
            if node_name not in stream_state.visited_nodes:
                stream_state.visited_nodes.append(node_name)
            
            # Remove from active_cluster_ids if this was an analyst_node (for report flow)
            # This ensures cluster highlighting updates correctly when tasks are finalized
            if flow == "report" and node_name == "analyst_node":
                metadata = task_info.get("metadata", {})
                file_id = metadata.get("file_id")
                if file_id:
                    stream_state.active_cluster_ids.discard(file_id)
    
    # Clear active_tasks after ending them
    stream_state.active_tasks.clear()
    
    # Additional safeguard: ensure splitter_node and batch_processor_node have node_end events
    # This handles cases where nodes started but on_chain_end was never received
    # Check both visited_nodes and nodes that might be in the initial next array
    ended_node_names = {task.get("node_name") for task in stream_state.task_history if task.get("ended_at")}
    
    # Check nodes that need node_end events
    nodes_to_check = set()
    # Add from visited_nodes
    nodes_to_check.update(stream_state.visited_nodes)
    # Also check for splitter_node and batch_processor_node specifically (they might not be in visited_nodes
    # if on_chain_start was never received, but node_start events were still emitted)
    nodes_to_check.add("splitter_node")
    nodes_to_check.add("batch_processor_node")
    
    for node_name in nodes_to_check:
        # For splitter_node and batch_processor_node specifically, ensure they have node_end
        if node_name in ("splitter_node", "batch_processor_node") and node_name not in ended_node_names:
            # Check if node_start was ever emitted for this node
            # If not, emit node_start first so frontend can match the node_end
            node_has_start = any(
                task.get("node_name") == node_name 
                for task in stream_state.task_history
            )
            
            if not node_has_start:
                # Emit node_start first (frontend needs both start and end to match)
                stream_state.event_seq += 1
                yield _create_envelope_event(
                    event_type=EVENT_NODE_START,
                    thread_id=thread_id,
                    flow=flow,
                    event_seq=stream_state.event_seq,
                    run_id=node_name,
                    payload={
                        "node": node_name,
                        "input_preview": None,
                    },
                )
                # Add to task_history to track it
                stream_state.task_history.append({
                    "node_name": node_name,
                    "run_id": node_name,
                    "started_at": time.time(),
                    "input_preview": None,
                })
                # Add to visited_nodes so it appears in final snapshot
                if node_name not in stream_state.visited_nodes:
                    stream_state.visited_nodes.append(node_name)
            
            # Emit node_end for this node (use node_name as run_id for consistency)
            stream_state.event_seq += 1
            yield _create_envelope_event(
                event_type=EVENT_NODE_END,
                thread_id=thread_id,
                flow=flow,
                event_seq=stream_state.event_seq,
                run_id=node_name,
                payload={
                    "node": node_name,
                    "output_preview": None,
                },
            )
            # Update task_history to mark as ended
            for task in stream_state.task_history:
                if task.get("node_name") == node_name and not task.get("ended_at"):
                    task["ended_at"] = time.time()
                    task["output_preview"] = None
                    break
            else:
                # If no task found, add new one
                stream_state.task_history.append({
                    "node_name": node_name,
                    "run_id": node_name,
                    "ended_at": time.time(),
                    "output_preview": None,
                })
            # Ensure node is in visited_nodes for final snapshot
            if node_name not in stream_state.visited_nodes:
                stream_state.visited_nodes.append(node_name)
    
    # Send final state snapshot
    try:
        stream_state.snapshot_seq += 1
        stream_state.event_seq += 1
        final_snapshot = await create_state_snapshot(
            graph, config, thread_id, flow, stream_state.visited_nodes,
            stream_state.active_tasks, stream_state.task_history, stream_state.snapshot_seq
        )
        if final_snapshot:
            # Ensure next array is empty in final snapshot (graph has completed)
            # Also explicitly remove splitter_node and batch_processor_node if they somehow got in
            next_nodes = final_snapshot.get("next", [])
            if isinstance(next_nodes, list):
                # Remove splitter_node and batch_processor_node explicitly
                next_nodes = [n for n in next_nodes if n not in ("splitter_node", "batch_processor_node")]
            final_snapshot["next"] = []
            
            yield _create_envelope_event(
                event_type=EVENT_STATE_SNAPSHOT,
                thread_id=thread_id,
                flow=flow,
                event_seq=stream_state.event_seq,
                payload=final_snapshot,
            )
    except Exception as e:
        logger.debug(
            "failed_to_get_final_snapshot",
            error=str(e),
            error_type=type(e).__name__,
            thread_id=thread_id,
        )


async def process_async_stream_events(
    graph: "CompiledGraph",
    initial_state: dict[str, Any],
    config: dict[str, Any],
    thread_id: str,
    org: str,
    project: str,
    accumulated_content_ref: dict[str, str] | None = None,
    flow: str = "chat",
) -> AsyncIterator[str]:
    """
    Process astream_events() and yield SSE strings directly.
    
    This runs entirely in the FastAPI event loop, so checkpointer operations
    work natively without event loop synchronization issues.
    
    The function is organized into three phases:
    1. Initialization: Set up state, send initial events
    2. Event loop: Process all events from astream_events()
    3. Finalization: Send final snapshot
    
    Args:
        graph: Compiled LangGraph instance
        initial_state: Initial agent state
        config: Graph configuration
        thread_id: Thread identifier
        org: Organization name
        project: Project name
        accumulated_content_ref: Optional mutable dict to store accumulated content
                                (key: "content"). If provided, will be updated as chunks arrive.
        flow: Flow type ("chat" or "report") to determine what state to extract
        
    Yields:
        SSE-formatted strings (compatible with FastAPI StreamingResponse)
    """
    # Initialize stream state
    stream_state, flow_policy, event_seq, snapshot_seq = _initialize_stream_state(
        initial_state, config, thread_id, flow
    )
    stream_state.event_seq = event_seq
    stream_state.snapshot_seq = snapshot_seq
    
    # Send graph_start event
    stream_state.event_seq += 1
    yield _create_envelope_event(
        event_type=EVENT_GRAPH_START,
        thread_id=thread_id,
        flow=flow,
        event_seq=stream_state.event_seq,
    )
    
    # Send initial state snapshot for report flow
    if flow == "report" and "raw_procedures" in initial_state:
        stream_state.snapshot_seq += 1
        stream_state.event_seq += 1
        initial_report_state = {
            "raw_procedures": initial_state.get("raw_procedures", []),
        }
        # Include pending_clusters if available in initial_state
        if "pending_clusters" in initial_state:
            initial_report_state["pending_clusters"] = initial_state.get("pending_clusters", [])
        # Include clusters_all if available (for UI display)
        if "clusters_all" in initial_state:
            initial_report_state["clusters_all"] = initial_state.get("clusters_all", [])
        yield _create_envelope_event(
            event_type=EVENT_STATE_SNAPSHOT,
            thread_id=thread_id,
            flow=flow,
            event_seq=stream_state.event_seq,
            payload={
                "snapshot_id": extract_snapshot_id(config, stream_state.snapshot_seq),
                "next": ["splitter_node"],
                "visited_nodes": [],
                "report_state": initial_report_state,
                "cluster_status": {
                    "active_cluster_ids": [],
                    "completed_cluster_ids": [],
                },
                "task_history": [],
            },
        )
    
    # Process main event loop
    async for event_str in _process_event_loop(
        graph, initial_state, config, thread_id, org, project, flow,
        flow_policy, stream_state, accumulated_content_ref
    ):
        yield event_str
    
    # Finalize stream
    async for event_str in _finalize_stream(graph, config, thread_id, flow, stream_state):
        yield event_str


def _process_tool_event_async(
    event: dict[str, Any],
    event_type: str,
    thread_id: str,
    visited_nodes: list[str],
    org: str,
    project: str,
    flow: str,
    run_id: str,
) -> list[dict[str, Any]]:
    """Process tool events and return list of events to yield."""
    events = []
    tool_data = extract_tool_event_data(event, event_type)
    
    if not tool_data:
        return events
    
    tool_name = tool_data.get("tool_name", "unknown")
    tool_to_node_map = get_tool_to_node_map(org, project)
    tool_node_name = tool_to_node_map.get(tool_name, f"tool_{tool_name}")
    
    # Track individual tool node
    if tool_node_name not in visited_nodes:
        visited_nodes.append(tool_node_name)
        
        # Emit node_start for the tool
        events.append({
            "type": EVENT_NODE_START,
            "node": tool_node_name,
            "thread_id": thread_id,
            "run_id": run_id if run_id else None,
        })
    
    # Emit tool_start or tool_end event
    tool_event = {
        "type": EVENT_TOOL_START if event_type == "on_tool_start" else EVENT_TOOL_END,
        "tool_name": tool_name,
        "args_preview": tool_data.get("args_preview", ""),
        "result_preview": tool_data.get("result_preview", "") if event_type == "on_tool_end" else "",
        "thread_id": thread_id,
        "run_id": run_id if run_id else None,
    }
    events.append(tool_event)
    
    # Emit node_end when tool ends
    if event_type == "on_tool_end":
        events.append({
            "type": EVENT_NODE_END,
            "node": tool_node_name,
            "thread_id": thread_id,
            "run_id": run_id if run_id else None,
        })
    
    return events


def _process_node_event_async(
    event: dict[str, Any],
    event_type: str,
    thread_id: str,
    current_node: str | None,
    visited_nodes: list[str],
    flow: str,
    active_tasks: dict[str, dict[str, Any]],
    task_history: list[dict[str, Any]],
    active_cluster_ids: set[str],
    flow_policy: FlowPolicy,
    run_id: str,
) -> NodeEventResult:
    """
    Process node events using FlowPolicy and active_tasks tracking.
    
    This function handles both sequential and parallel node execution. For parallel
    execution (e.g., Send() in report flow), each task has its own run_id which is
    tracked separately in active_tasks.
    
    Args:
        event: LangGraph event dictionary
        event_type: "on_chain_start" or "on_chain_end"
        thread_id: Thread identifier
        current_node: Currently active node (for sequential flows)
        visited_nodes: List of visited node names
        flow: Flow type ("chat" or "report")
        active_tasks: Dict of active tasks keyed by run_id (mutated)
        task_history: List of all tasks (mutated)
        active_cluster_ids: Set of active cluster IDs (mutated)
        flow_policy: FlowPolicy instance for flow-specific behavior
        run_id: Run ID from event (may be empty for sequential nodes)
        
    Returns:
        NodeEventResult with updated state
    """
    import time
    
    events: list[dict[str, Any]] = []
    node_name = event.get("name", "")
    should_snapshot = False
    
    # Early returns for invalid or filtered nodes
    if not node_name:
        return NodeEventResult(
            events=events,
            current_node=current_node,
            visited_nodes=visited_nodes,
            active_tasks=active_tasks,
            task_history=task_history,
            active_cluster_ids=active_cluster_ids,
            should_snapshot=False,
        )
    
    # Use FlowPolicy to filter nodes
    if not flow_policy.node_filter(node_name):
        return NodeEventResult(
            events=events,
            current_node=current_node,
            visited_nodes=visited_nodes,
            active_tasks=active_tasks,
            task_history=task_history,
            active_cluster_ids=active_cluster_ids,
            should_snapshot=False,
        )
    
    # For chat flow, check metadata to filter out internal chains
    if flow == "chat" and event_type == "on_chain_start":
        metadata = event.get("metadata", {})
        langgraph_node = metadata.get("langgraph_node")
        if langgraph_node is not None and langgraph_node != node_name:
            # This is likely an internal chain/subgraph, skip it
            return NodeEventResult(
                events=events,
                current_node=current_node,
                visited_nodes=visited_nodes,
                active_tasks=active_tasks,
                task_history=task_history,
                active_cluster_ids=active_cluster_ids,
                should_snapshot=False,
            )
    
    # Handle chain start (node start)
    if event_type == "on_chain_start":
        # Extract run_id (each Send() instance has its own run_id)
        # For parallel execution (e.g., Send() in report flow), each task instance
        # gets a unique run_id from LangGraph. For sequential nodes, we may need to
        # construct a run_id from the node name.
        # Extract run_id with node_name for consistency - this ensures better matching
        # during node_end for nodes like batch_processor_node that may run multiple times
        extracted_run_id = _extract_run_id(event, node_name)
        if extracted_run_id:
            run_id = extracted_run_id
        elif not run_id:
            # Fallback: use node_name as run_id for sequential nodes without explicit run_id
            run_id = node_name
        
        # Track task in active_tasks for parallel task tracking
        # This allows us to track multiple concurrent instances of the same node
        # (e.g., multiple analyst_node tasks processing different clusters)
        started_at = time.time()
        data = event.get("data", {})
        input_data = data.get("input", {}) if isinstance(data, dict) else {}
        
        # Use FlowPolicy to extract preview and metadata
        preview_data = {"input": input_data, "node_name": node_name}
        input_preview = flow_policy.extract_input_preview(preview_data)
        metadata = flow_policy.extract_metadata(preview_data)
        
        # Store task info in active_tasks dict keyed by run_id
        # This enables tracking of parallel tasks independently
        task_info: dict[str, Any] = {
            "node_name": node_name,
            "run_id": run_id,
            "started_at": started_at,
            "input_preview": input_preview,
            "metadata": metadata,
        }
        active_tasks[run_id] = task_info
        
        # Extract file_id for report flow cluster tracking
        # When analyst_node starts, we track which cluster (file_id) is being processed
        # This enables the frontend to highlight the correct cluster in StateView
        if flow == "report" and "file_id" in metadata:
            file_id = metadata["file_id"]
            if file_id:
                active_cluster_ids.add(file_id)
        
        # Update visited nodes
        if node_name not in visited_nodes:
            visited_nodes.append(node_name)
        
        # Update current_node (for sequential nodes, not parallel)
        # For parallel nodes (report flow), we don't clear current_node because
        # multiple nodes can be active simultaneously
        if flow != "report" or current_node is None:
            current_node = node_name
        
        # Emit node_start event
        events.append({
            "type": EVENT_NODE_START,
            "node": node_name,
            "thread_id": thread_id,
            "run_id": run_id,
            "input_preview": input_preview,
        })
    
    # Handle chain end (node end + state update)
    elif event_type == "on_chain_end":
        # Find task by run_id or node_name
        # For parallel tasks, we match by run_id. For sequential tasks that don't
        # have explicit run_ids, we fall back to matching by node_name.
        task_info = None
        task_run_id = run_id
        
        # Re-extract run_id consistently with how it was stored (using node_name)
        # The run_id passed in might have been extracted without node_name in the event loop,
        # but we stored it WITH node_name during node_start. So we need to try both formats.
        run_id_with_name = _extract_run_id(event, node_name)
        
        # Try to find task in active_tasks by run_id (try both formats)
        # For nodes using Send objects, the run_id format might differ between
        # on_chain_start and on_chain_end events, so we try multiple formats
        if task_run_id and task_run_id in active_tasks:
            task_info = active_tasks[task_run_id]
        elif run_id_with_name and run_id_with_name in active_tasks:
            task_info = active_tasks[run_id_with_name]
            task_run_id = run_id_with_name
        elif run_id and run_id in active_tasks:
            # Try the original run_id without node_name prefix
            task_info = active_tasks[run_id]
            task_run_id = run_id
        else:
            # Fallback: find by node_name (for sequential nodes without explicit run_id)
            # For nodes like batch_processor_node that may be called multiple times,
            # find the most recent one that hasn't ended (by started_at timestamp)
            # This is critical for nodes using Send objects where run_id matching might fail
            # Also try matching by stripping node_name prefix from stored run_ids
            most_recent_task = None
            most_recent_run_id = None
            most_recent_started_at = 0.0
            
            # First, try to find by exact node_name match (most recent unended task)
            for tid, tinfo in active_tasks.items():
                if tinfo.get("node_name") == node_name and not tinfo.get("ended_at"):
                    started_at = tinfo.get("started_at", 0.0)
                    if started_at > most_recent_started_at:
                        most_recent_task = tinfo
                        most_recent_run_id = tid
                        most_recent_started_at = started_at
            
            # If no match found, try matching by run_id format (strip node_name prefix)
            # This handles cases where run_id was stored with node_name prefix but
            # event provides it without prefix (or vice versa)
            if not most_recent_task and run_id:
                for tid, tinfo in active_tasks.items():
                    if tinfo.get("node_name") == node_name and not tinfo.get("ended_at"):
                        stored_run_id = tinfo.get("run_id", "")
                        # Check if stored run_id matches event run_id (with or without prefix)
                        if stored_run_id == run_id or stored_run_id.endswith(f"_{run_id}") or run_id.endswith(f"_{stored_run_id}"):
                            started_at = tinfo.get("started_at", 0.0)
                            if started_at > most_recent_started_at:
                                most_recent_task = tinfo
                                most_recent_run_id = tid
                                most_recent_started_at = started_at
            
            if most_recent_task:
                task_info = most_recent_task
                task_run_id = most_recent_run_id
                logger.debug(
                    "matched_task_by_node_name_fallback",
                    node_name=node_name,
                    matched_run_id=task_run_id,
                    original_run_id=run_id,
                    run_id_with_name=run_id_with_name,
                    thread_id=thread_id,
                )
        
        # If we still couldn't find the task, use the best available run_id for node_end event
        # This ensures we have a valid run_id even when task matching fails
        if not task_run_id:
            task_run_id = run_id_with_name if run_id_with_name else run_id
        
        # Extract output preview using FlowPolicy
        data = event.get("data", {})
        output_data = data.get("output", {}) if isinstance(data, dict) else {}
        preview_data = {"output": output_data, "node_name": node_name}
        output_preview = flow_policy.extract_output_preview(preview_data)
        
        # Update task info and move to history
        # When a task completes, we:
        # 1. Mark it as ended with timestamp
        # 2. Add it to task_history for inspection/restore
        # 3. Remove it from active_tasks
        # 4. Update cluster tracking if applicable
        ended_at = time.time()
        if task_info:
            task_info["ended_at"] = ended_at
            task_info["output_preview"] = output_preview
            # Move to task_history for inspection/restore capability
            task_history.append(task_info.copy())
            # Remove from active_tasks
            active_tasks.pop(task_run_id, None)
            
            # Remove from active_cluster_ids if this was an analyst_node
            # This ensures cluster highlighting updates correctly when tasks complete
            if flow == "report" and node_name == "analyst_node":
                metadata = task_info.get("metadata", {})
                file_id = metadata.get("file_id")
                if file_id:
                    active_cluster_ids.discard(file_id)
        
        # Always emit node_end (handles parallel execution and nodes using Send objects)
        # Even if we couldn't find the task in active_tasks, we still emit node_end
        # to ensure the frontend receives completion events for all nodes.
        # This is critical for nodes like splitter_node and batch_processor_node that
        # use Send objects for routing, as they may complete before their on_chain_end
        # events are properly matched.
        # If we still don't have a run_id after all fallbacks, extract one more time
        if not task_run_id:
            task_run_id = _extract_run_id(event, node_name)
        
        # Always emit node_end event, even if task matching failed
        # This ensures nodes are marked as completed in the frontend
        node_end_event = {
            "type": EVENT_NODE_END,
            "node": node_name,
            "thread_id": thread_id,
            "run_id": task_run_id if task_run_id else None,
            "output_preview": output_preview,
        }
        events.append(node_end_event)
        
        # If we couldn't find the task but the node_name is valid, ensure it's marked as visited
        # This handles edge cases where on_chain_end arrives but task wasn't tracked
        if not task_info and node_name:
            # Try to find any task with this node_name in active_tasks and mark it as ended
            # This is a safety net for nodes that may have been missed during tracking
            for tid, tinfo in list(active_tasks.items()):
                if tinfo.get("node_name") == node_name:
                    # Found a matching task, mark it as ended and move to history
                    tinfo["ended_at"] = ended_at
                    tinfo["output_preview"] = output_preview
                    task_history.append(tinfo.copy())
                    active_tasks.pop(tid, None)
                    # Update cluster tracking if applicable
                    if flow == "report" and node_name == "analyst_node":
                        metadata = tinfo.get("metadata", {})
                        file_id = metadata.get("file_id")
                        if file_id:
                            active_cluster_ids.discard(file_id)
                    break
        
        # Log if we couldn't find the task (helps debug missing on_chain_end events)
        # This can happen for nodes using Send objects where run_id matching fails
        if not task_info:
            active_node_names = [t.get("node_name") for t in active_tasks.values()]
            logger.debug(
                "node_end_without_matching_task",
                node_name=node_name,
                run_id=task_run_id,
                original_run_id=run_id,
                run_id_with_name=run_id_with_name,
                active_tasks_count=len(active_tasks),
                active_node_names=active_node_names,
                thread_id=thread_id,
            )
        
        # Update visited nodes
        if node_name not in visited_nodes:
            visited_nodes.append(node_name)
        
        # Update current_node
        if current_node == node_name:
            current_node = None
        
        # Mark that we should emit a snapshot after this node_end
        # Snapshots are checkpoint-authoritative and provide the definitive state
        # after each node completes, ensuring frontend state stays in sync
        should_snapshot = True
        
    # Return results
    return NodeEventResult(
        events=events,
        current_node=current_node,
        visited_nodes=visited_nodes,
        active_tasks=active_tasks,
        task_history=task_history,
        active_cluster_ids=active_cluster_ids,
        should_snapshot=should_snapshot,
    )


