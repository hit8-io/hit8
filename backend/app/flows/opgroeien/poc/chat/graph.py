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
    NODE_PROCEDURES_VECTOR_SEARCH,
    NODE_REGELGEVING_VECTOR_SEARCH,
)
from app.flows.opgroeien.poc.chat.tools import (
    get_all_tools,
    procedures_vector_search,
    regelgeving_vector_search,
)
from app.flows.opgroeien.poc.chat.tools_utils import create_tool_node
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


def _get_tool_node_name_map() -> dict[str, str]:
    """
    Get mapping of tool names to node names for active tools only.
    
    Returns:
        Dictionary mapping tool names to their corresponding node names
    """
    return {
        "procedures_vector_search": NODE_PROCEDURES_VECTOR_SEARCH,
        "regelgeving_vector_search": NODE_REGELGEVING_VECTOR_SEARCH,
        # Future tools can be added here when enabled in tools.py
    }


def route_to_tool(state: AgentState) -> str:
    """Route to the appropriate tool node based on tool calls."""
    last_message = state["messages"][-1]
    
    # Check if the last message has tool calls
    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        return END
    
    # Get the first tool call (handle multiple tool calls by routing to first one)
    # In a more advanced implementation, you could handle parallel tool execution
    tool_call = last_message.tool_calls[0]
    tool_name = tool_call.get("name", "")
    
    # Map tool names to node names
    tool_node_map = _get_tool_node_name_map()
    node_name = tool_node_map.get(tool_name, END)
    
    logger.debug(
        "routing_to_tool",
        tool_name=tool_name,
        node_name=node_name,
        tool_call_id=tool_call.get("id"),
    )
    
    return node_name


def _get_tool_node_function_map() -> dict[str, tuple[str, Callable[..., Any]]]:
    """
    Get mapping of tool names to (node_name, function) tuples for active tools only.
    
    Returns:
        Dictionary mapping tool names to (node_name, function) tuples
    """
    return {
        "procedures_vector_search": (NODE_PROCEDURES_VECTOR_SEARCH, procedures_vector_search),
        "regelgeving_vector_search": (NODE_REGELGEVING_VECTOR_SEARCH, regelgeving_vector_search),
        # Future tools can be added here when enabled in tools.py
    }


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
    
    # Get tool node mapping (only includes active tools)
    tool_node_map = _get_tool_node_function_map()
    
    # Add nodes only for tools that are actually in the tools list
    routing_map = {END: END}
    for tool in tools:
        tool_name = tool.name
        if tool_name in tool_node_map:
            node_name, tool_func = tool_node_map[tool_name]
            graph.add_node(node_name, create_tool_node(tool_name, tool_func))
            routing_map[node_name] = node_name
            logger.debug(
                "added_tool_node",
                tool_name=tool_name,
                node_name=node_name,
            )
    
    # Add edges (START is automatically the entry point when used in add_edge)
    graph.add_edge(START, NODE_AGENT)
    
    # Conditional edge from agent: route to specific tool node or END
    graph.add_conditional_edges(
        NODE_AGENT,
        route_to_tool,
        routing_map,
    )
    
    # After each tool, loop back to agent
    for tool in tools:
        tool_name = tool.name
        if tool_name in tool_node_map:
            node_name, _ = tool_node_map[tool_name]
            graph.add_edge(node_name, NODE_AGENT)
    
    return graph.compile(checkpointer=_agent_checkpointer)
