"""
Constants for API routes and streaming.

These constants are shared across multiple API modules.
Constants used in only one file should be defined in that file.
"""
from __future__ import annotations

# Event types for Server-Sent Events
# Used in streaming.py and routes/chat.py
EVENT_GRAPH_START = "graph_start"
EVENT_NODE_START = "node_start"
EVENT_NODE_END = "node_end"
EVENT_GRAPH_END = "graph_end"
EVENT_ERROR = "error"
EVENT_CONTENT_CHUNK = "content_chunk"
EVENT_LLM_START = "llm_start"
EVENT_LLM_END = "llm_end"
EVENT_TOOL_START = "tool_start"
EVENT_TOOL_END = "tool_end"
EVENT_STATE_UPDATE = "state_update"

