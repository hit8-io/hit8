"""
Constants for API routes and streaming.
"""
from __future__ import annotations

# Queue item types for streaming
QUEUE_EVENT = "__event__"
QUEUE_CHUNK = "__chunk__"
QUEUE_ERROR = "__error__"

# Event types for Server-Sent Events
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

# Node names (for simple agent)
NODE_GENERATE = "generate"

