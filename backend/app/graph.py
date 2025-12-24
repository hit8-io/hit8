"""
LangGraph state machine for chat orchestration.
"""
from __future__ import annotations

import json
from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from typing import Any
from langchain_google_vertexai import ChatVertexAI
from google.oauth2 import service_account

from app.config import settings

# Define the agent state
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], "The conversation messages"]
    context: Annotated[str, "Retrieved context for the current query"]


def retrieve_node(state: AgentState) -> AgentState:
    """
    Retrieve relevant context (mock implementation for MVP).
    
    In a full implementation, this would query Supabase vector store.
    """
    # Mock retrieval - in production, query Supabase vector store
    state["context"] = "Mock context: This is a placeholder for vector search results."
    return state


def generate_node(state: AgentState) -> AgentState:
    """
    Generate response using Google Vertex AI (Gemini Pro).
    """
    # Get service account JSON from settings (with fallback support)
    service_account_json = settings.get_vertex_service_account()
    
    if not service_account_json:
        raise ValueError("Vertex AI service account must be set via VERTEX_HIT8_POC_IAM_GSERVICEACCOUNT_COM environment variable")
    
    # Parse the service account JSON
    service_account_info = json.loads(service_account_json)
    
    # Create credentials from service account info
    creds = service_account.Credentials.from_service_account_info(
        service_account_info
    )
    
    # Initialize the Vertex AI model
    # Using Gemini 3 Pro with global location (required for gemini-3-pro-preview)
    # Model name: gemini-3-pro-preview (official Vertex AI name)
    # Temperature should NOT be set for Gemini 3 Pro (use default 1.0)
    # 
    # Note: Gemini 3 Pro preview requires global location access
    # If you get 404 errors, ensure:
    # 1. Gemini 3 Pro is enabled in your GCP project
    # 2. Your service account has Vertex AI User permissions
    
    model = ChatVertexAI(
        model_name=settings.vertex_ai_model_name,
        project=service_account_info.get("project_id") or settings.gcp_project,
        location=settings.vertex_ai_location,
        credentials=creds,
        # Do not set temperature - use default 1.0 for Gemini 3 Pro
    )
    
    # Get the last human message
    messages = state["messages"]
    last_message = messages[-1] if messages else None
    
    if not last_message or not isinstance(last_message, HumanMessage):
        state["messages"].append(AIMessage(content="I didn't receive a valid message."))
        return state
    
    # Build context-aware prompt
    context = state.get("context", "")
    
    # Create a system message with context and user message
    from langchain_core.messages import SystemMessage
    system_message = SystemMessage(content=f"Context: {context}")
    
    # Invoke with messages
    response = model.invoke([system_message, last_message])
    
    # Add AI response to messages
    if isinstance(response, BaseMessage):
        state["messages"].append(response)
    else:
        state["messages"].append(AIMessage(content=str(response)))
    
    return state


def create_graph() -> Any:
    """
    Create and compile the LangGraph state machine.
    """
    graph = StateGraph(AgentState)
    
    # Add nodes
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("generate", generate_node)
    
    # Define the flow
    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)
    
    # Compile the graph
    return graph.compile()

