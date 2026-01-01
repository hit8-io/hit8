"""
Pydantic models for API requests and responses.
"""
from __future__ import annotations

from pydantic import BaseModel


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    message: str
    thread_id: str | None = None


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""
    response: str
    user_id: str
    thread_id: str

