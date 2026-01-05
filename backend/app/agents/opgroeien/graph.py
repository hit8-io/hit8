"""
LangGraph agent with tools and memory for the n8n workflow conversion.
"""
from __future__ import annotations

import json
import operator
from typing import TYPE_CHECKING, Annotated, Optional, TypedDict

import structlog
from google.oauth2 import service_account
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_google_genai import ChatGoogleGenerativeAI
import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from app.agents.common import get_langfuse_handler
from app.agents.opgroeien.constants import NODE_AGENT, NODE_TOOLS
from app.agents.opgroeien.tools import get_all_tools
from app.config import get_metadata, settings
from app.prompts.loader import get_system_prompt

if TYPE_CHECKING:
    from langfuse import Langfuse
    from langfuse.langchain import CallbackHandler
    from langgraph.graph import CompiledGraph

logger = structlog.get_logger(__name__)


class AgentState(TypedDict):
    """State for the agent graph with messages and memory."""
    messages: Annotated[list[BaseMessage], operator.add]


# Cache model and credentials at module level
_agent_model: ChatGoogleGenerativeAI | None = None

# Store checkpointer reference for history access
_agent_checkpointer: PostgresSaver | None = None
_agent_checkpointer_cm: object | None = None

def get_agent_checkpointer() -> PostgresSaver | None:
    """Get the checkpointer instance."""
    return _agent_checkpointer


def _get_agent_model() -> ChatGoogleGenerativeAI:
    """Get or create cached Vertex AI model for agent."""
    global _agent_model
    if _agent_model is None:
        service_account_info = json.loads(settings.vertex_service_account_json)
        if "project_id" not in service_account_info:
            raise ValueError("project_id is required in service account JSON")
        project_id = service_account_info["project_id"]
        if not project_id:
            raise ValueError("project_id cannot be empty in service account JSON")
        
        creds = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=['https://www.googleapis.com/auth/cloud-platform']
        )
        
        # Use thinking_level instead of temperature
        model_kwargs = {
            "provider": "vertexai",
            "thinking_level": "medium",  # Can be configured via settings if needed
        }
        
        _agent_model = ChatGoogleGenerativeAI(
            model=settings.vertex_ai_model_name,
            model_kwargs=model_kwargs,
            project=project_id,
            location=settings.vertex_ai_location,
            credentials=creds,
        )
    return _agent_model


def agent_node(state: AgentState, config: Optional[RunnableConfig] = None) -> AgentState:
    """Agent node that processes messages and may call tools."""
    model = _get_agent_model()
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
    
    # Check if system message is already in messages
    has_system_message = any(isinstance(msg, SystemMessage) for msg in messages)
    
    # Prepend system message if not present
    if not has_system_message:
        system_prompt = get_system_prompt()
        messages = [SystemMessage(content=system_prompt)] + messages
    
    # Filter and validate messages before invoking model
    # Ensure all messages have valid content (ToolMessages should be handled by LangChain automatically)
    # But Google GenAI might have issues with empty or malformed ToolMessages
    filtered_messages = []
    message_types = []
    for msg in messages:
        msg_type = type(msg).__name__
        message_types.append(msg_type)
        
        # Skip messages without content (shouldn't happen, but safety check)
        if hasattr(msg, "content") and msg.content is None:
            logger.warning(
                "skipping_message_without_content",
                message_type=msg_type,
            )
            continue
        
        # ToolMessages should have content - if not, log a warning
        if isinstance(msg, ToolMessage):
            content = getattr(msg, "content", None)
            tool_call_id = getattr(msg, "tool_call_id", None)
            if not content:
                logger.warning(
                    "tool_message_missing_content",
                    tool_call_id=tool_call_id,
                    message_type=msg_type,
                )
                continue
            # Log ToolMessage details for debugging
            logger.debug(
                "tool_message_included",
                tool_call_id=tool_call_id,
                content_length=len(str(content)) if content else 0,
            )
        
        filtered_messages.append(msg)
    
    if not filtered_messages:
        logger.error(
            "no_valid_messages_after_filtering",
            original_message_count=len(messages),
            original_message_types=message_types,
        )
        raise ValueError("No valid messages to send to model")
    
    # Log message details before invoking model
    logger.debug(
        "invoking_model_with_messages",
        message_count=len(filtered_messages),
        message_types=[type(m).__name__ for m in filtered_messages],
        has_tool_messages=any(isinstance(m, ToolMessage) for m in filtered_messages),
    )
    
    # Google GenAI requires at least one HumanMessage or AIMessage (not just ToolMessages)
    # If we only have SystemMessage and ToolMessages, we need to ensure we have context
    has_human_or_ai = any(isinstance(m, (HumanMessage, AIMessage)) for m in filtered_messages)
    if not has_human_or_ai and any(isinstance(m, ToolMessage) for m in filtered_messages):
        logger.error(
            "missing_human_or_ai_message",
            message_count=len(filtered_messages),
            message_types=[type(m).__name__ for m in filtered_messages],
        )
        raise ValueError(
            "Cannot invoke model with only ToolMessages. State must include HumanMessage or AIMessage for context."
        )
    
    # Convert config to dict for metadata injection
    config_dict: dict[str, Any] = {}
    if config is not None:
        config_dict = dict(config) if isinstance(config, dict) else {}
    
    # Inject centralized metadata into config for Vertex AI
    metadata = get_metadata()
    if "metadata" not in config_dict:
        config_dict["metadata"] = {}
    config_dict["metadata"].update(metadata)
    
    # Invoke model with filtered messages
    try:
        response = model_with_tools.invoke(filtered_messages, config=config_dict if config_dict else config)
    except Exception as e:
        logger.error(
            "model_invoke_failed",
            error=str(e),
            error_type=type(e).__name__,
            message_count=len(filtered_messages),
            message_types=[type(m).__name__ for m in filtered_messages],
        )
        raise
    
    # Return state with new response appended
    # LangGraph will automatically merge this with existing state when using Annotated[list[...], ...]
    # But to be safe, we preserve all existing messages and append the new response
    # This ensures the full conversation history is maintained
    return {"messages": state["messages"] + [response]}


def should_continue(state: AgentState) -> str:
    """Determine if we should continue to tools or end."""
    last_message = state["messages"][-1]
    
    # Check if the last message has tool calls
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return NODE_TOOLS
    return END


def create_agent_graph() -> CompiledGraph:
    """Create and compile the LangGraph agent state machine."""
    global _agent_checkpointer, _agent_checkpointer_cm
    
    # Initialize PostgreSQL checkpointer for persistent state storage
    # 
    # Connection Pooler Compatibility:
    # - Supabase and other connection poolers (PgBouncer) don't support prepared statements
    # - We disable prepared statements by setting prepare_threshold=None
    # - This allows the connection to work with transaction-level pooling
    # - Connection errors after successful operations are handled gracefully in chat streaming
    try:
        # Create connection with prepare_threshold=None to disable prepared statements
        # This is required for Supabase connection pooling which doesn't support prepared statements
        conn = psycopg.connect(
            settings.database_connection_string,
            prepare_threshold=None,  # Disable prepared statements for connection pooling
        )
        # Enable autocommit for setup() - CREATE INDEX CONCURRENTLY cannot run in a transaction
        conn.autocommit = True
        # PostgresSaver can be initialized with a connection object directly
        _agent_checkpointer = PostgresSaver(conn)
        _agent_checkpointer.setup()
        # Disable autocommit after setup for normal operations
        conn.autocommit = False
        # Store connection as context manager to keep it alive for the application lifetime
        _agent_checkpointer_cm = conn
        logger.info(
            "agent_postgres_checkpointer_initialized",
            database_url=settings.database_connection_string.split("@")[-1] if "@" in settings.database_connection_string else "configured",
            connection_pooler_compatible=True,
        )
    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)
        logger.error(
            "agent_postgres_checkpointer_init_failed",
            error=error_msg,
            error_type=error_type,
            database_url=settings.database_connection_string.split("@")[-1] if "@" in settings.database_connection_string else "configured",
            hint="Check database connection string and network connectivity. Ensure connection pooler (if used) supports transaction-level pooling.",
        )
        raise
    
    # Get all tools
    tools = get_all_tools()
    
    # Create tool node
    tool_node = ToolNode(tools)
    
    # Create graph
    graph = StateGraph(AgentState)
    
    # Add nodes
    graph.add_node(NODE_AGENT, agent_node)
    graph.add_node(NODE_TOOLS, tool_node)
    
    # Add edges (START is automatically the entry point when used in add_edge)
    graph.add_edge(START, NODE_AGENT)
    
    # Conditional edge from agent: if tool calls exist, go to tools, else END
    graph.add_conditional_edges(
        NODE_AGENT,
        should_continue,
        {
            NODE_TOOLS: NODE_TOOLS,
            END: END,
        }
    )
    
    # After tools, loop back to agent
    graph.add_edge(NODE_TOOLS, NODE_AGENT)
    
    return graph.compile(checkpointer=_agent_checkpointer)

