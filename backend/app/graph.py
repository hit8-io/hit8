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


def generate_node(state: AgentState) -> AgentState:
    """Generate response using Google Vertex AI."""
    service_account_info = json.loads(settings.vertex_service_account_json)
    creds = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=['https://www.googleapis.com/auth/cloud-platform']
    )
    
    model = ChatGoogleGenerativeAI(
        model=settings.vertex_ai_model_name,
        model_kwargs={"provider": "vertexai"},
        project=service_account_info.get("project_id") or settings.gcp_project,
        location=settings.vertex_ai_location,
        credentials=creds,
    )
    
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

