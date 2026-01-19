"""
LangGraph state machine for chat orchestration.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, TypedDict

import structlog
from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

from app.api.checkpointer import get_checkpointer
from app.flows.common import get_agent_model, _wrap_with_retry
from app.flows.hit8.hit8 import constants as flow_constants
from app.config import settings

if TYPE_CHECKING:
    from langgraph.graph import CompiledGraph

logger = structlog.get_logger(__name__)


class AgentState(TypedDict):
    """State for the chat flow."""
    messages: Annotated[list[BaseMessage], "The conversation messages"]


def generate_node(
    state: AgentState, 
    config: RunnableConfig | None = None
) -> AgentState:
    """Generate response using Google Vertex AI.
    
    Args:
        state: Current agent state with messages
        config: Optional runtime configuration
        
    Returns:
        Updated state with AI response appended
    """
    # Extract model_name from config if provided
    model_name = None
    if config:
        # Try multiple ways to access configurable
        if hasattr(config, "configurable"):
            if isinstance(config.configurable, dict):
                model_name = config.configurable.get("model_name")
            elif hasattr(config.configurable, "get"):
                model_name = config.configurable.get("model_name")
        # Also try accessing as dict
        if not model_name and isinstance(config, dict):
            configurable = config.get("configurable", {})
            if isinstance(configurable, dict):
                model_name = configurable.get("model_name")
    
    model = get_agent_model(model_name=model_name)
    last_message = state["messages"][-1]
    
    # Prepare config with metadata for Vertex AI
    config_dict: dict = dict(config) if config else {}
    if "metadata" not in config_dict:
        config_dict["metadata"] = {}
    # Start with settings metadata (environment, account)
    config_dict["metadata"].update(settings.metadata)
    # Add flow-specific org and project from constants
    config_dict["metadata"]["org"] = flow_constants.ORG
    config_dict["metadata"]["project"] = flow_constants.PROJECT
    
    # Apply retry wrapper for direct model invocation
    model_with_retry = _wrap_with_retry(model)
    # Generate response with metadata injection
    response = model_with_retry.invoke([last_message], config=config_dict)
    state["messages"].append(response)
    
    return state


def create_graph() -> CompiledGraph:
    """Create and compile the LangGraph state machine.
    
    Returns:
        Compiled graph ready for execution
    """
    # Get checkpointer (initialized at application startup via FastAPI lifespan)
    checkpointer = get_checkpointer()
    
    graph = StateGraph(AgentState)
    graph.add_node("generate", generate_node)
    graph.set_entry_point("generate")
    graph.add_edge("generate", END)
    
    return graph.compile(checkpointer=checkpointer)

