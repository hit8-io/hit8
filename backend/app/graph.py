"""
LangGraph state machine for chat orchestration.
"""
from __future__ import annotations

import json
import os
from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from typing import Any
from langchain_google_genai import ChatGoogleGenerativeAI
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
    
    Uses the unified ChatGoogleGenerativeAI class with provider="vertexai"
    to target Vertex AI backend. Handles authentication for both environments:
    - Cloud Run: Uses Application Default Credentials (ADC) automatically
    - Local/Doppler: Uses explicit service account JSON credentials
    """
    # Check if we're running on Cloud Run (ADC will be used automatically)
    is_cloud_run = os.environ.get("K_SERVICE") is not None
    
    creds = None
    project_id = settings.gcp_project
    
    if not is_cloud_run:
        # Local/Doppler: Get service account JSON from settings
        service_account_json = settings.get_vertex_service_account()
        
        if not service_account_json:
            raise ValueError(
                "Vertex AI service account must be set via "
                "VERTEX_HIT8_POC_IAM_GSERVICEACCOUNT_COM environment variable"
            )
        
        # Parse the service account JSON
        service_account_info = json.loads(service_account_json)
        
        # Create credentials from service account info with Vertex AI scopes
        creds = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=['https://www.googleapis.com/auth/cloud-platform']
        )
        
        # Extract project ID from service account if available
        project_id = service_account_info.get("project_id") or settings.gcp_project
    
    # Initialize the unified ChatGoogleGenerativeAI model with Vertex AI provider
    # Using Gemini 3 Pro/Flash with location (e.g., europe-west1, global)
    # Model name: gemini-3-pro-preview or gemini-3-flash-preview
    # Temperature should NOT be set for Gemini 3 Pro (use default 1.0)
    # 
    # Note: The provider="vertexai" flag switches backend to Vertex AI (GCP)
    # - On Cloud Run: credentials=None uses ADC (Application Default Credentials)
    # - Local/Doppler: credentials=creds uses explicit service account
    # If you get 404 errors, ensure:
    # 1. Gemini 3 Pro is enabled in your GCP project
    # 2. Your service account has Vertex AI User permissions
    # 3. The location matches your project's Vertex AI region
    
    model = ChatGoogleGenerativeAI(
        model=settings.vertex_ai_model_name,  # Note: 'model' not 'model_name'
        provider="vertexai",  # CRITICAL: Switches backend to Vertex AI
        project=project_id,
        location=settings.vertex_ai_location,
        credentials=creds,  # None on Cloud Run (uses ADC), explicit creds on local/Doppler
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

