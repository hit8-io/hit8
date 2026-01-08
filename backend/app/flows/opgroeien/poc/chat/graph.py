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
    NODE_EXTRACT_ENTITIES,
    NODE_FETCH_WEBPAGE,
    NODE_GENERATE_DOCX,
    NODE_GENERATE_XLSX,
    NODE_GET_PROCEDURE,
    NODE_GET_REGELGEVING,
    NODE_PROCEDURES_VECTOR_SEARCH,
    NODE_QUERY_KNOWLEDGE_GRAPH,
    NODE_REGELGEVING_VECTOR_SEARCH,
)
from app.flows.opgroeien.poc.chat.tools import (
    extract_entities,
    fetch_website,
    generate_docx,
    generate_xlsx,
    get_all_tools,
    get_procedure,
    get_regelgeving,
    procedures_vector_search,
    query_knowledge_graph,
    regelgeving_vector_search,
)
from app.flows.opgroeien.poc.chat.tools.utils import create_tool_node
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
    
    # Check if there are any AIMessages with tool calls that don't have all ToolMessages
    # If so, don't invoke the model - just return empty state and let routing handle it
    for msg in messages:
        if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
            tool_call_ids = []
            for tc in msg.tool_calls:
                if isinstance(tc, dict):
                    tool_call_ids.append(tc.get("id", ""))
                else:
                    tool_call_ids.append(getattr(tc, "id", ""))
            tool_message_ids = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}
            missing_responses = [tid for tid in tool_call_ids if tid not in tool_message_ids]
            
            if missing_responses:
                # There are pending tool calls - don't invoke the model, just return empty state
                # The routing function will handle routing to the next tool
                logger.debug(
                    "agent_node_skipping_invoke_pending_tool_calls",
                    missing_responses=missing_responses,
                    total_tool_calls=len(tool_call_ids),
                    responded_tool_calls=len(tool_message_ids),
                )
                return {"messages": []}  # Return empty to not add anything to state
    
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
        "fetch_website": NODE_FETCH_WEBPAGE,
        "get_procedure": NODE_GET_PROCEDURE,
        "get_regelgeving": NODE_GET_REGELGEVING,
        "extract_entities": NODE_EXTRACT_ENTITIES,
        "query_knowledge_graph": NODE_QUERY_KNOWLEDGE_GRAPH,
        "generate_docx": NODE_GENERATE_DOCX,
        "generate_xlsx": NODE_GENERATE_XLSX,
        # Future tools can be added here when enabled in tools.py
    }


def route_to_tool(state: AgentState) -> str:
    """Route to the appropriate tool node based on tool calls.
    
    Handles multiple tool calls by checking which tools still need responses.
    Routes to the first tool that hasn't been responded to yet.
    
    Priority:
    1. Check the most recent AIMessage for new tool calls
    2. If none, check previous AIMessages for pending tool calls
    """
    # First, check the most recent AIMessage (might be the last message or before a ToolMessage)
    last_message = state["messages"][-1]
    
    # If the last message is an AIMessage with tool calls, use those (new tool calls)
    if isinstance(last_message, AIMessage) and hasattr(last_message, "tool_calls") and last_message.tool_calls:
        ai_message_with_tool_calls = last_message
        logger.debug(
            "routing_to_tool_found_new_ai_message",
            tool_calls_count=len(last_message.tool_calls),
            last_message_type="AIMessage",
        )
    else:
        # Otherwise, find the last AIMessage with tool calls (pending tool calls from previous turn)
        ai_message_with_tool_calls = None
        for msg in reversed(state["messages"]):
            if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
                ai_message_with_tool_calls = msg
                logger.debug(
                    "routing_to_tool_found_previous_ai_message",
                    tool_calls_count=len(msg.tool_calls),
                    last_message_type=type(last_message).__name__,
                )
                break
    
    # If no AIMessage with tool calls found, we're done
    if ai_message_with_tool_calls is None:
        return END
    
    # Get all tool call IDs that have already been responded to
    responded_tool_call_ids = set()
    for msg in state["messages"]:
        if isinstance(msg, ToolMessage):
            responded_tool_call_ids.add(msg.tool_call_id)
    
    # Find the first tool call that hasn't been responded to
    tool_node_map = _get_tool_node_name_map()
    
    for tool_call in ai_message_with_tool_calls.tool_calls:
        # Handle both dict and object formats for tool_call
        tool_call_id = tool_call.get("id", "") if isinstance(tool_call, dict) else getattr(tool_call, "id", "")
        if tool_call_id not in responded_tool_call_ids:
            tool_name = tool_call.get("name", "") if isinstance(tool_call, dict) else getattr(tool_call, "name", "")
            node_name = tool_node_map.get(tool_name, END)
            
            logger.debug(
                "routing_to_tool",
                tool_name=tool_name,
                node_name=node_name,
                tool_call_id=tool_call_id,
                total_tool_calls=len(ai_message_with_tool_calls.tool_calls),
                pending_tool_calls=len(ai_message_with_tool_calls.tool_calls) - len(responded_tool_call_ids),
                is_new_ai_message=(ai_message_with_tool_calls is last_message),
            )
            
            return node_name
    
    # All tool calls have been responded to
    return END


def _get_tool_node_function_map() -> dict[str, tuple[str, Callable[..., Any]]]:
    """
    Get mapping of tool names to (node_name, function) tuples for active tools only.
    
    Returns:
        Dictionary mapping tool names to (node_name, function) tuples
    """
    return {
        "procedures_vector_search": (NODE_PROCEDURES_VECTOR_SEARCH, procedures_vector_search),
        "regelgeving_vector_search": (NODE_REGELGEVING_VECTOR_SEARCH, regelgeving_vector_search),
        "fetch_website": (NODE_FETCH_WEBPAGE, fetch_website),
        "get_procedure": (NODE_GET_PROCEDURE, get_procedure),
        "get_regelgeving": (NODE_GET_REGELGEVING, get_regelgeving),
        "extract_entities": (NODE_EXTRACT_ENTITIES, extract_entities),
        "query_knowledge_graph": (NODE_QUERY_KNOWLEDGE_GRAPH, query_knowledge_graph),
        "generate_docx": (NODE_GENERATE_DOCX, generate_docx),
        "generate_xlsx": (NODE_GENERATE_XLSX, generate_xlsx),
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
    # The routing function ensures all tool calls get responses by checking
    # which tool calls haven't been responded to yet
    graph.add_conditional_edges(
        NODE_AGENT,
        route_to_tool,
        routing_map,
    )
    
    # After each tool, loop back to agent (which will route to next pending tool if any)
    for tool in tools:
        tool_name = tool.name
        if tool_name in tool_node_map:
            node_name, _ = tool_node_map[tool_name]
            graph.add_edge(node_name, NODE_AGENT)
    
    return graph.compile(checkpointer=_agent_checkpointer)
