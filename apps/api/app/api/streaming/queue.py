"""
Queue processing functions.
"""
from __future__ import annotations

import asyncio
import json
import queue
import threading
from collections.abc import AsyncIterator
from typing import Any

import structlog

from app.api.constants import EVENT_CONTENT_CHUNK, EVENT_ERROR
from app.api.streaming.constants import QUEUE_CHUNK, QUEUE_ERROR, QUEUE_EVENT

logger = structlog.get_logger(__name__)


def process_chunk(
    chunk: dict[str, Any], final_response_ref: list[str | None]
) -> str | None:
    """Process a chunk and update final response reference.
    
    Args:
        chunk: Chunk dictionary
        final_response_ref: Reference to store final response
        
    Returns:
        SSE string to yield, or None if chunk should be skipped
    """
    if isinstance(chunk, dict) and chunk.get("type") == EVENT_CONTENT_CHUNK:
        if "accumulated" in chunk:
            final_response_ref[0] = chunk["accumulated"]
        return f"data: {json.dumps(chunk)}\n\n"
    
    if chunk.get("__final_content__"):
        if "content" in chunk:
            final_response_ref[0] = chunk["content"]
        return None  # Skip final content marker
    
    if chunk.get("__final_state__"):
        return None  # Skip final state marker
    
    return None


async def process_stream_queue(
    event_queue: queue.Queue,
    stream_done: threading.Event,
    final_response_ref: list[str | None],
    thread_id: str | None = None,
) -> AsyncIterator[str]:
    """Process events and chunks from the stream queue."""
    while True:
        if stream_done.is_set() and event_queue.empty():
            break
        
        try:
            item = event_queue.get(timeout=0.1)
            item_type, item_data = item
            
            if item_type == QUEUE_ERROR:
                error_obj = item_data
                error_message = str(error_obj) if error_obj else "Unknown error occurred"
                error_type = type(error_obj).__name__ if error_obj else "UnknownError"
                
                logger.error(
                    "stream_queue_error",
                    error=error_message,
                    error_type=error_type,
                    thread_id=thread_id,
                )
                
                error_data = {
                    "type": EVENT_ERROR,
                    "error": error_message,
                    "error_type": error_type,
                    "thread_id": thread_id,
                }
                yield f"data: {json.dumps(error_data)}\n\n"
                break
            
            if item_type == QUEUE_EVENT:
                yield f"data: {json.dumps(item_data)}\n\n"
                continue
            
            if item_type == QUEUE_CHUNK:
                sse_str = process_chunk(item_data, final_response_ref)
                if sse_str:
                    yield sse_str
                continue
                
        except queue.Empty:
            if stream_done.is_set() and event_queue.empty():
                break
            await asyncio.sleep(0.01)
            continue
        except Exception as e:
            raise
