"""
Utility functions for API endpoints.
"""
from __future__ import annotations

from typing import Any

from fastapi import Request
from langchain_core.messages import BaseMessage, HumanMessage

from app.config import settings


def get_cors_headers(request: Request) -> dict[str, str]:
    """Get CORS headers for the given request."""
    origin = request.headers.get("origin")
    headers: dict[str, str] = {}
    if origin and origin in settings.CORS_ALLOW_ORIGINS:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
    return headers


def extract_message_content(content: Any) -> str:
    """Extract message content, handling various formats."""
    if isinstance(content, list):
        # If content is a list (e.g., from multimodal responses), join or take first
        if not content:
            # Empty list should return empty string, not "[]"
            return ""
        
        # Try to extract text from all blocks in the list
        text_parts = []
        for block in content:
            if isinstance(block, dict) and "text" in block:
                text = block.get("text", "")
                if text:
                    text_parts.append(str(text))
            elif isinstance(block, str) and block:
                text_parts.append(block)
        
        if text_parts:
            # Join all text parts if multiple blocks found
            return "".join(text_parts)
        
        # If list has items but none matched expected format, return empty string
        # instead of string representation of the list
        return ""
    elif not isinstance(content, str):
        return str(content)
    return content


def extract_ai_message(messages: list[BaseMessage]) -> BaseMessage:
    """Extract the last AI message from the message list."""
    ai_messages = [msg for msg in messages if not isinstance(msg, HumanMessage)]
    if not ai_messages:
        raise ValueError("No AI response generated")
    return ai_messages[-1]


def serialize_message(msg: Any) -> dict[str, Any]:
    """Serialize a single message to dictionary format."""
    from langchain_core.messages import AIMessage, ToolMessage
    import json
    
    msg_dict: dict[str, Any] = {"type": type(msg).__name__}
    
    if hasattr(msg, "content"):
        msg_dict["content"] = str(msg.content) if msg.content is not None else ""
    
    if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
        msg_dict["tool_calls"] = []
        for tool_call in msg.tool_calls:
            tool_call_dict: dict[str, Any] = {}
            if hasattr(tool_call, "name"):
                tool_call_dict["name"] = tool_call.name
            if hasattr(tool_call, "args"):
                tool_call_dict["args"] = tool_call.args
            if hasattr(tool_call, "id"):
                tool_call_dict["id"] = tool_call.id
            if hasattr(tool_call, "function"):
                func = tool_call.function
                if hasattr(func, "name"):
                    tool_call_dict["name"] = func.name
                if hasattr(func, "arguments"):
                    try:
                        tool_call_dict["args"] = json.loads(func.arguments)
                    except (json.JSONDecodeError, TypeError):
                        tool_call_dict["args"] = func.arguments
            msg_dict["tool_calls"].append(tool_call_dict)
    
    if isinstance(msg, ToolMessage):
        if hasattr(msg, "tool_call_id"):
            msg_dict["tool_call_id"] = msg.tool_call_id
        if hasattr(msg, "name"):
            msg_dict["name"] = msg.name
    
    if hasattr(msg, "response_metadata") and msg.response_metadata:
        metadata = msg.response_metadata
        if isinstance(metadata, dict):
            usage = metadata.get("token_usage") or metadata.get("usage_metadata")
            if usage:
                msg_dict["usage_metadata"] = usage
    
    return msg_dict


def serialize_messages(state: Any) -> list[dict[str, Any]]:
    """Serialize messages from state to dictionary format."""
    messages = []
    if hasattr(state, "values") and "messages" in state.values:
        for msg in state.values["messages"]:
            messages.append(serialize_message(msg))
    return messages

