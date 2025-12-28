"""
LangGraph state machine for chat orchestration.
"""
from __future__ import annotations

import json
from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from typing import Any
from langchain_google_genai import ChatGoogleGenerativeAI
from google.oauth2 import service_account
import structlog

from app.config import settings, get_metadata

logger = structlog.get_logger(__name__)

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], "The conversation messages"]


# Cache model and credentials at module level
_model: ChatGoogleGenerativeAI | None = None

# Store checkpointer reference for history access
_checkpointer: MemorySaver | None = None

def get_checkpointer() -> MemorySaver | None:
    """Get the checkpointer instance."""
    return _checkpointer

# Initialize Langfuse client if enabled
if settings.langfuse_enabled:
    try:
        from langfuse import Langfuse
        import os
        
        # Validator ensures these are not None when langfuse_enabled is True
        assert settings.langfuse_public_key is not None
        assert settings.langfuse_secret_key is not None
        assert settings.langfuse_base_url is not None
        
        env = "prd" if os.getenv("ENVIRONMENT") == "prd" else "dev"
        
        Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_base_url,
        )
        logger.info(
            "langfuse_client_initialized",
            env=env,
            base_url=settings.langfuse_base_url,
        )
    except Exception as e:
        logger.error(
            "langfuse_client_init_failed",
            error=str(e),
            error_type=type(e).__name__,
            env=os.getenv("ENVIRONMENT", "unknown"),
        )


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


def _get_langfuse_handler() -> Any | None:
    """Get Langfuse callback handler if enabled, None otherwise."""
    if not settings.langfuse_enabled:
        return None
    
    try:
        from langfuse.langchain import CallbackHandler
        # CallbackHandler uses the singleton client initialized at module level
        handler = CallbackHandler()
        logger.debug("langfuse_callback_handler_created")
        return handler
    except Exception as e:
        logger.warning(
            "langfuse_callback_handler_creation_failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        return None


def generate_node(state: AgentState, config: RunnableConfig | None = None) -> AgentState:
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


def create_graph() -> Any:
    """Create and compile the LangGraph state machine."""
    global _checkpointer
    graph = StateGraph(AgentState)
    graph.add_node("generate", generate_node)
    graph.set_entry_point("generate")
    graph.add_edge("generate", END)
    
    # Add checkpointer to enable state retrieval by thread_id
    _checkpointer = MemorySaver()
    return graph.compile(checkpointer=_checkpointer)

