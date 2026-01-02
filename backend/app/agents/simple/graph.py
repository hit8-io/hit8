"""
LangGraph state machine for chat orchestration.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Annotated, Optional, TypedDict

import structlog
from google.oauth2 import service_account
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_google_genai import ChatGoogleGenerativeAI
import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, StateGraph

from app.agents.common import get_langfuse_handler
from app.config import get_metadata, settings

if TYPE_CHECKING:
    from langgraph.graph import CompiledGraph

logger = structlog.get_logger(__name__)

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], "The conversation messages"]


# Cache model and credentials at module level
_model: ChatGoogleGenerativeAI | None = None

# Store checkpointer reference for history access
_checkpointer: PostgresSaver | None = None
# Store context manager to keep connection alive
_checkpointer_cm: object | None = None

def get_checkpointer() -> PostgresSaver | None:
    """Get the checkpointer instance."""
    return _checkpointer

# Langfuse utilities moved to app.agents.common


def _get_model() -> ChatGoogleGenerativeAI:
    """Get or create cached Vertex AI model."""
    global _model
    if _model is None:
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
        
        _model = ChatGoogleGenerativeAI(
            model=settings.vertex_ai_model_name,
            model_kwargs={"provider": "vertexai"},
            project=project_id,
            location=settings.vertex_ai_location,
            credentials=creds,
        )
    return _model


# Langfuse handler moved to app.agents.common.get_langfuse_handler()


def generate_node(state: AgentState, config: Optional[RunnableConfig] = None) -> AgentState:
    """Generate response using Google Vertex AI."""
    model = _get_model()
    last_message = state["messages"][-1]
    
    # Convert config to dict for metadata injection
    # RunnableConfig is a TypedDict, so we can safely convert it
    config_dict: dict[str, Any] = {}
    if config is not None:
        # RunnableConfig is a TypedDict, convert to regular dict
        config_dict = dict(config) if isinstance(config, dict) else {}
    
    # Inject centralized metadata into config for Vertex AI
    metadata = get_metadata()
    if "metadata" not in config_dict:
        config_dict["metadata"] = {}
    # Merge centralized metadata with existing metadata
    config_dict["metadata"].update(metadata)
    
    # Pass config directly to model.invoke - LangGraph/LangChain will handle callbacks propagation
    # According to official docs: https://langfuse.com/integrations/frameworks/langchain
    # Convert back to RunnableConfig type for type safety
    response = model.invoke([last_message], config=config_dict if config_dict else config)
    
    state["messages"].append(response)
    
    return state


def create_graph() -> CompiledGraph:
    """Create and compile the LangGraph state machine."""
    global _checkpointer, _checkpointer_cm
    
    # Initialize PostgreSQL checkpointer for persistent state storage
    # Disable prepared statements for Supabase connection pooling compatibility
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
        _checkpointer = PostgresSaver(conn)
        # Initialize database schema (idempotent - safe to call multiple times)
        _checkpointer.setup()
        # Disable autocommit after setup for normal operations
        conn.autocommit = False
        # Store connection to keep it alive for the application lifetime
        _checkpointer_cm = conn
        logger.info(
            "postgres_checkpointer_initialized",
            database_url=settings.database_connection_string.split("@")[-1] if "@" in settings.database_connection_string else "configured",
        )
    except Exception as e:
        logger.error(
            "postgres_checkpointer_init_failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        raise
    
    graph = StateGraph(AgentState)
    graph.add_node("generate", generate_node)
    graph.set_entry_point("generate")
    graph.add_edge("generate", END)
    
    return graph.compile(checkpointer=_checkpointer)

