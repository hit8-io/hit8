"""
LangGraph agent with tools and memory.
"""
from __future__ import annotations

import operator
from typing import TYPE_CHECKING, Annotated, Any, Callable, Optional, TypedDict

import structlog
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.flows.common import get_agent_model, get_langfuse_handler
from app.flows.opgroeien.poc import constants as flow_constants
from app.flows.opgroeien.poc.constants import (
    NODE_AGENT,
    NODE_TOOLS,
)
from app.flows.opgroeien.poc.chat.tools import (
    get_all_tools,
)
from app.config import settings

if TYPE_CHECKING:
    from langfuse import Langfuse
    from langfuse.langchain import CallbackHandler
    from langgraph.graph import CompiledGraph

logger = structlog.get_logger(__name__)


class AgentState(TypedDict):
    """State for the agent graph with messages and memory."""
    messages: Annotated[list[BaseMessage], operator.add]


_agent_checkpointer: MemorySaver | None = None


def get_agent_checkpointer() -> MemorySaver | None:
    """Get the checkpointer instance."""
    return _agent_checkpointer


def agent_node(state: AgentState, config: Optional[RunnableConfig] = None) -> AgentState:
    """Agent node that processes messages and may call tools."""
    model = get_agent_model()
    tools = get_all_tools()
    
    # Bind tools to model
    model_with_tools = model.bind_tools(tools)
    
    # Get messages from state
    messages = state["messages"]
    
    # Log all messages in state for debugging
    logger.debug(
        "agent_node_state_messages",
        message_count=len(messages),
        message_types=[type(m).__name__ for m in messages],
        has_human=any(isinstance(m, HumanMessage) for m in messages),
        has_ai=any(isinstance(m, AIMessage) for m in messages),
        has_tool=any(isinstance(m, ToolMessage) for m in messages),
    )
    
    # Convert config to dict for metadata injection
    config_dict: dict[str, Any] = dict(config) if config is not None else {}
    
    # Inject metadata into config for Vertex AI
    # Use flow constants for org/project, settings for environment/account
    if "metadata" not in config_dict:
        config_dict["metadata"] = {}
    # Start with settings metadata (environment, account)
    config_dict["metadata"].update(settings.metadata)
    # Add flow-specific org and project from constants
    config_dict["metadata"]["org"] = flow_constants.ORG
    config_dict["metadata"]["project"] = flow_constants.PROJECT
    
    # Invoke model with messages
    try:
        response = model_with_tools.invoke(messages, config=config_dict)
    except Exception as e:
        logger.error(
            "model_invoke_failed",
            error=str(e),
            error_type=type(e).__name__,
            message_count=len(messages),
            message_types=[type(m).__name__ for m in messages],
        )
        raise
    
    # Return state with new response appended
    # LangGraph will automatically merge this with existing state when using Annotated[list[...], ...]
    return {"messages": state["messages"] + [response]}


def route_to_tool(state: AgentState) -> str:
    """Route to tools node if there are tool calls, otherwise END."""
    last_message = state["messages"][-1]
    
    # Check if the last message has tool calls
    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        return END
    
    # Log all tool calls for debugging
    tool_names = [tc.get("name", "") for tc in last_message.tool_calls]
    logger.debug(
        "routing_to_tools",
        tool_count=len(last_message.tool_calls),
        tool_names=tool_names,
    )
    
    # Route to unified tools node that will process all tool calls
    return NODE_TOOLS


def tools_node(state: AgentState) -> AgentState:
    """Unified tools node that processes all tool calls in the last message.
    
    This ensures that every tool call gets a response, which is required by Vertex AI.
    """
    last_message = state["messages"][-1]
    
    # Check if the last message has tool calls
    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        logger.warning("tools_node_called_without_tool_calls")
        return state
    
    # Get all tools and create a mapping
    tools = get_all_tools()
    tool_map = {tool.name: tool for tool in tools}
    
    # Process all tool calls
    tool_messages = []
    for tool_call in last_message.tool_calls:
        tool_name = tool_call.get("name", "")
        tool_call_id = tool_call.get("id", "")
        
        if tool_name not in tool_map:
            logger.warning(
                "unknown_tool_called",
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                available_tools=list(tool_map.keys()),
            )
            tool_messages.append(
                ToolMessage(
                    content=f"Error: Unknown tool '{tool_name}'",
                    tool_call_id=tool_call_id
                )
            )
            continue
        
        tool_func = tool_map[tool_name]
        
        try:
            logger.info(
                "tool_executing",
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                args=tool_call.get("args", {}),
            )
            
            # Execute the tool with the provided arguments
            # StructuredTool objects need to be invoked, not called directly
            result = tool_func.invoke(tool_call.get("args", {}))
            
            # Create ToolMessage
            tool_messages.append(
                ToolMessage(
                    content=str(result),
                    tool_call_id=tool_call_id
                )
            )
            
            logger.info(
                "tool_success",
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                result_length=len(str(result)),
            )
        except Exception as e:
            logger.error(
                "tool_error",
                tool_name=tool_name,
                error=str(e),
                error_type=type(e).__name__,
                tool_call_id=tool_call_id,
            )
            tool_messages.append(
                ToolMessage(
                    content=f"Error: {str(e)}",
                    tool_call_id=tool_call_id
                )
            )
    
    logger.info(
        "tools_node_completed",
        tool_call_count=len(last_message.tool_calls),
        tool_message_count=len(tool_messages),
    )
    
    return {"messages": state["messages"] + tool_messages}


def create_agent_graph() -> CompiledGraph:
    """Create and compile the LangGraph agent state machine.
    
    Note: We use MemorySaver instead of PostgresSaver. See docs/debt.md for details.
    """
    global _agent_checkpointer
    
    if _agent_checkpointer is None:
        _agent_checkpointer = MemorySaver()
        logger.info(
            "agent_memory_checkpointer_initialized",
            checkpointer_type="MemorySaver",
        )
    
    # Get all tools
    tools = get_all_tools()
    
    # Create graph
    graph = StateGraph(AgentState)
    
    # Add agent node
    graph.add_node(NODE_AGENT, agent_node)
    
    # Add unified tools node that processes all tool calls
    graph.add_node(NODE_TOOLS, tools_node)
    
    # Add edges (START is automatically the entry point when used in add_edge)
    graph.add_edge(START, NODE_AGENT)
    
    # Conditional edge from agent: route to tools node if there are tool calls, otherwise END
    graph.add_conditional_edges(
        NODE_AGENT,
        route_to_tool,
        {
            NODE_TOOLS: NODE_TOOLS,
            END: END,
        },
    )
    
    # After tools node, loop back to agent
    graph.add_edge(NODE_TOOLS, NODE_AGENT)
    
    return graph.compile(checkpointer=_agent_checkpointer)
