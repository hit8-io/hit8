"""
Main streaming orchestration functions.
"""
from __future__ import annotations

import asyncio
import queue
import threading
from typing import Any

import structlog

from app.api.graph_manager import get_graph
from app.api.streaming.constants import QUEUE_ERROR
from app.api.streaming.events import process_events_queue
from app.api.streaming.finalize import finalize_stream

logger = structlog.get_logger(__name__)


def stream(
    initial_state: dict[str, Any],
    config: dict[str, Any],
    thread_id: str,
    event_queue: queue.Queue,
    stream_done: threading.Event,
    stream_error: list[Exception | None],
    org: str,
    project: str,
) -> None:
    """Stream content, LLM/tool events, and node tracking using astream_events() v2 only.
    
    Uses astream_events(version="v2") for all event types including content chunks,
    LLM events, tool events, and node tracking.
    """
    accumulated_content = ""
    last_ai_message_content = ""
    visited_nodes: list[str] = []
    current_node: str | None = None
    
    try:
        # Initialize execution metrics tracking
        try:
            from app.api.observability import initialize_execution
            initialize_execution(thread_id)
        except Exception:
            # Don't fail if observability is not available
            pass
        
        logger.info(
            "stream_started",
            thread_id=thread_id,
            initial_message_count=len(initial_state.get("messages", [])),
        )
        
        graph = get_graph(org, project)
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Single queue for events
        events_queue: asyncio.Queue = asyncio.Queue()
        events_done = threading.Event()
        async_error: Exception | None = None
        
        async def stream_events():
            """Stream all events from astream_events v2."""
            nonlocal async_error
            try:
                async for event in graph.astream_events(initial_state, config=config, version="v2"):
                    await events_queue.put(event)
            except Exception as e:
                async_error = e
            finally:
                events_done.set()
        
        # Start single stream
        events_task = loop.create_task(stream_events())
        
        try:
            # Process events queue until done
            while True:
                stream_done_check = events_done.is_set()
                queue_empty = events_queue.empty()
                
                if stream_done_check and queue_empty:
                    break
                
                # Run event loop briefly to process async tasks
                loop.run_until_complete(asyncio.sleep(0))
                
                # Process all event types
                result = process_events_queue(
                    events_queue, event_queue, thread_id,
                    accumulated_content, last_ai_message_content,
                    current_node, visited_nodes, org, project
                )
                if result:
                    accumulated_content, last_ai_message_content, current_node, visited_nodes = result
            
            # Check for async errors
            if async_error:
                raise async_error
        finally:
            # Clean up
            if not events_task.done():
                events_task.cancel()
                try:
                    loop.run_until_complete(events_task)
                except asyncio.CancelledError:
                    pass
            loop.close()
        
        # Finalize stream: send final state and content
        finalize_stream(
            event_queue, thread_id, config,
            current_node, visited_nodes,
            accumulated_content, last_ai_message_content,
            org, project
        )
            
    except Exception as e:
        stream_error[0] = e
        event_queue.put((QUEUE_ERROR, e))
        logger.exception(
            "stream_error",
            error=str(e),
            error_type=type(e).__name__,
            thread_id=thread_id,
            exc_info=True,
        )
    finally:
        # Finalize execution metrics tracking
        try:
            from app.api.observability import finalize_execution
            finalize_execution(thread_id)
        except Exception:
            # Don't fail if observability is not available
            pass
        
        logger.info("stream_finally", thread_id=thread_id)
        stream_done.set()


def create_stream_thread(
    initial_state: dict[str, Any],
    config: dict[str, Any],
    thread_id: str,
    event_queue: queue.Queue,
    stream_done: threading.Event,
    org: str,
    project: str,
) -> tuple[list[threading.Thread], list[Exception | None]]:
    """Create and start streaming thread using astream_events() v2 only."""
    from app.api.constants import EVENT_GRAPH_START
    from app.api.streaming.constants import QUEUE_EVENT
    
    event_queue.put((QUEUE_EVENT, {"type": EVENT_GRAPH_START, "thread_id": thread_id}))
    
    stream_error: list[Exception | None] = [None]
    stream_errors = [stream_error]
    
    stream_thread = threading.Thread(
        target=stream,
        args=(initial_state, config, thread_id, event_queue, stream_done, stream_error, org, project),
        daemon=True,
    )
    stream_thread.start()
    
    return [stream_thread], stream_errors
