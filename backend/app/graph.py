"""
LangGraph state machine for chat orchestration.
"""
from __future__ import annotations

import json
from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import StateGraph, END
from typing import Any
from langchain_google_genai import ChatGoogleGenerativeAI
from google.oauth2 import service_account

from app.config import settings

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], "The conversation messages"]


# Cache model and credentials at module level
_model: ChatGoogleGenerativeAI | None = None


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


def generate_node(state: AgentState) -> AgentState:
    """Generate response using Google Vertex AI."""
    model = _get_model()
    last_message = state["messages"][-1]
    response = model.invoke([last_message])
    state["messages"].append(response)
    
    return state


def create_graph() -> Any:
    """Create and compile the LangGraph state machine."""
    graph = StateGraph(AgentState)
    graph.add_node("generate", generate_node)
    graph.set_entry_point("generate")
    graph.add_edge("generate", END)
    return graph.compile()

