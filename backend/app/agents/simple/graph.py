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
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.agents.common import get_langfuse_handler
from app.config import settings

if TYPE_CHECKING:
    from langgraph.graph import CompiledGraph

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

# Langfuse utilities moved to app.agents.common


def _get_model() -> ChatGoogleGenerativeAI:
    """Get or create cached Vertex AI model."""
    global _model
    if _model is None:
        service_account_info = json.loads(settings.vertex_service_account)
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
    if "metadata" not in config_dict:
        config_dict["metadata"] = {}
    # Merge centralized metadata with existing metadata
    config_dict["metadata"].update(settings.metadata)
    
    # Pass config directly to model.invoke - LangGraph/LangChain will handle callbacks propagation
    # According to official docs: https://langfuse.com/integrations/frameworks/langchain
    # Convert back to RunnableConfig type for type safety
    response = model.invoke([last_message], config=config_dict if config_dict else config)
    
    state["messages"].append(response)
    
    return state


def create_graph() -> CompiledGraph:
    """Create and compile the LangGraph state machine."""
    global _checkpointer
    
    # Checkpointer Selection: MemorySaver
    #
    # We use MemorySaver instead of PostgresSaver because:
    # 1. PostgresSaver doesn't fully support async checkpoint operations
    #    - `aget_tuple()` raises NotImplementedError
    #    - This forced us to use sync `stream()` in background threads
    # 2. MemorySaver supports both sync and async operations
    #    - Enables future migration to async streaming if needed
    #    - Simpler architecture without database dependencies
    # 3. Trade-off: State is not persisted across restarts
    #    - Acceptable for current use case (stateless conversations)
    #    - Can migrate back to PostgresSaver when async support is added
    
    if _checkpointer is None:
        _checkpointer = MemorySaver()
        logger.info(
            "memory_checkpointer_initialized",
            checkpointer_type="MemorySaver",
        )
    
    graph = StateGraph(AgentState)
    graph.add_node("generate", generate_node)
    graph.set_entry_point("generate")
    graph.add_edge("generate", END)
    
    return graph.compile(checkpointer=_checkpointer)

