"""
LangGraph state machine for chat orchestration.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, TypedDict

import structlog
from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.flows.common import get_agent_model
from app.flows.hit8.hit8 import constants as flow_constants
from app.config import settings

if TYPE_CHECKING:
    from langgraph.graph import CompiledGraph

logger = structlog.get_logger(__name__)


class AgentState(TypedDict):
    """State for the chat flow."""
    messages: Annotated[list[BaseMessage], "The conversation messages"]


# Module-level checkpointer cache
_checkpointer: MemorySaver | None = None


def get_checkpointer() -> MemorySaver | None:
    """Get the checkpointer instance."""
    return _checkpointer


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
    model = get_agent_model()
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
    
    # Generate response with metadata injection
    response = model.invoke([last_message], config=config_dict)
    state["messages"].append(response)
    
    return state


def create_graph() -> CompiledGraph:
    """Create and compile the LangGraph state machine.
    
    Returns:
        Compiled graph ready for execution
    """
    global _checkpointer
    
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

