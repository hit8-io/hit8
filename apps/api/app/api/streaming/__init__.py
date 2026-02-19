"""
Streaming package for chat endpoint.

The main implementation uses pure async in async_events.py.
"""
from __future__ import annotations

from app.api.streaming.finalize import extract_final_response

__all__ = [
    "extract_final_response",
]
