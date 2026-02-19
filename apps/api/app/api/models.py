"""
Pydantic models for API requests and responses.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    message: str = Field(..., min_length=1, max_length=100000, description="User message content")
    thread_id: str | None = Field(
        None,
        max_length=255,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Optional thread identifier for conversation continuity"
    )

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        """Validate message is not just whitespace."""
        if not v.strip():
            raise ValueError("Message cannot be empty or only whitespace")
        return v.strip()

    @field_validator("thread_id")
    @classmethod
    def validate_thread_id(cls, v: str | None) -> str | None:
        """Validate thread_id format if provided."""
        if v is not None:
            if len(v) == 0:
                raise ValueError("Thread ID cannot be empty string")
            if not v.strip():
                raise ValueError("Thread ID cannot be only whitespace")
        return v


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""
    response: str
    user_id: str
    thread_id: str

