"""
Utility functions for the opgroeien agent - tool node creation.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

import structlog
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from app.flows.common import extract_callbacks_from_config

if TYPE_CHECKING:
    from app.flows.opgroeien.poc.chat.graph import AgentState

logger = structlog.get_logger(__name__)

# Exported functions (used by other modules)
__all__ = ["create_tool_node"]


def create_tool_node(tool_name: str, tool_func: Callable[..., Any]):
    """Factory to create individual tool nodes."""
    def tool_node(state: "AgentState", config: RunnableConfig) -> "AgentState":
        """Execute a specific tool and return ToolMessage."""
        try:
            # Extract thread_id from config
            thread_id = None
            if config:
                # Try multiple ways to access configurable
                if hasattr(config, 'configurable'):
                    if isinstance(config.configurable, dict):
                        thread_id = config.configurable.get("thread_id")
                    elif hasattr(config.configurable, 'get'):
                        thread_id = config.configurable.get("thread_id")
                # Also try accessing as dict
                if not thread_id and isinstance(config, dict):
                    configurable = config.get("configurable", {})
                    if isinstance(configurable, dict):
                        thread_id = configurable.get("thread_id")
            
            # Fallback: Get thread_id from observability context variable if not in config
            if not thread_id:
                try:
                    from app.api.observability import _current_thread_id
                    thread_id = _current_thread_id.get()
                except Exception:
                    pass
            
            # Set thread_id in observability context for tools that need it (if we got it from config)
            if thread_id:
                try:
                    from app.api.observability import _current_thread_id
                    _current_thread_id.set(thread_id)
                except Exception:
                    pass
            
            # If thread_id not found, log warning (shouldn't happen in normal flow)
            if not thread_id:
                logger.warning(
                    f"tool_{tool_name}_no_thread_id",
                    tool_name=tool_name,
                )
            
            # Extract callbacks from config for Langfuse logging
            # Use helper function for consistent callback extraction
            callbacks = extract_callbacks_from_config(config)
            
            last_message = state["messages"][-1]
            
            # Find and execute tool calls for this specific tool
            tool_messages = []
            
            # Find the AIMessage with tool calls (not just use last_message)
            # The last message might be a ToolMessage from a previous tool execution
            ai_message_with_tool_calls = None
            for msg in reversed(state["messages"]):
                if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
                    ai_message_with_tool_calls = msg
                    break
            
            if ai_message_with_tool_calls is None:
                return {"messages": state["messages"]}
            
            # Get tool calls from the found AIMessage
            tool_calls_to_process = ai_message_with_tool_calls.tool_calls if hasattr(ai_message_with_tool_calls, "tool_calls") else []
            
            # Get already responded tool call IDs
            responded_tool_call_ids = set()
            for msg in state["messages"]:
                if isinstance(msg, ToolMessage):
                    responded_tool_call_ids.add(msg.tool_call_id)
            
            for tool_call in tool_calls_to_process:
                # Handle both dict and object formats for tool_call
                tool_call_name = tool_call.get("name") if isinstance(tool_call, dict) else getattr(tool_call, "name", None)
                if tool_call_name != tool_name:
                    continue
                    
                tool_call_id = tool_call.get("id", "") if isinstance(tool_call, dict) else getattr(tool_call, "id", "")
                
                # Skip if already responded to
                if tool_call_id in responded_tool_call_ids:
                    continue
                
                try:
                    logger.info(
                        f"tool_{tool_name}_executing",
                        tool_call_id=tool_call_id,
                        args=tool_call.get("args", {}) if isinstance(tool_call, dict) else getattr(tool_call, "args", {}),
                        thread_id=thread_id,
                    )
                    
                    # Prepare tool arguments
                    tool_args = tool_call.get("args", {}) if isinstance(tool_call, dict) else getattr(tool_call, "args", {})
                    
                    # Add thread_id to tools that need it (e.g., generate_docx, generate_xlsx, extract_entities)
                    if tool_name in ["generate_docx", "generate_xlsx", "extract_entities"] and thread_id:
                        tool_args["thread_id"] = thread_id
                    
                    # Add callbacks to tools that make LLM calls (e.g., extract_entities)
                    if tool_name == "extract_entities" and callbacks:
                        tool_args["callbacks"] = callbacks
                    
                    # Execute the tool with the provided arguments
                    # Handle both callable functions and StructuredTool objects
                    from langchain_core.tools import StructuredTool
                    if isinstance(tool_func, StructuredTool):
                        result = tool_func.invoke(tool_args)
                    else:
                        result = tool_func(**tool_args)
                    
                    # Create ToolMessage
                    tool_messages.append(
                        ToolMessage(
                            content=str(result),
                            tool_call_id=tool_call_id
                        )
                    )
                    
                    logger.info(
                        f"tool_{tool_name}_success",
                        tool_call_id=tool_call_id,
                        result_length=len(str(result)),
                        thread_id=thread_id,
                    )
                except Exception as e:
                    logger.error(
                        f"tool_{tool_name}_error",
                        error=str(e),
                        error_type=type(e).__name__,
                        tool_call_id=tool_call_id,
                        thread_id=thread_id,
                    )
                    tool_messages.append(
                        ToolMessage(
                            content=f"Error: {str(e)}",
                            tool_call_id=tool_call_id
                        )
                    )
            
            return {"messages": state["messages"] + tool_messages}
        except Exception as e:
            logger.error(
                f"tool_{tool_name}_node_exception",
                error=str(e),
                error_type=type(e).__name__,
            )
            # Return empty tool messages on error to avoid breaking the flow
            return {"messages": state["messages"]}
    
    return tool_node
