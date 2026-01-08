"""
Streaming package for chat endpoint.

Public API exports maintain backward compatibility with the original module structure.
"""
from __future__ import annotations

from app.api.streaming.core import create_stream_thread
from app.api.streaming.finalize import extract_final_response
from app.api.streaming.queue import process_stream_queue

__all__ = [
    "create_stream_thread",
    "extract_final_response",
    "process_stream_queue",
]
