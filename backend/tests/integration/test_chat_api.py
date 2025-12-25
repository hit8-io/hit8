"""
Integration tests for the chat API endpoint.
"""
import pytest
from unittest.mock import patch, MagicMock
from langchain_core.messages import HumanMessage, AIMessage


@pytest.mark.asyncio
async def test_chat_endpoint_success(client):
    """Test successful chat endpoint request."""
    # 1. Mock Auth (Bypass Google Token Check)
    from app.main import app
    from app.deps import verify_google_token
    
    async def mock_verify_token():
        return {"sub": "test_user_123"}
    
    app.dependency_overrides[verify_google_token] = mock_verify_token
    
    try:
        # 2. Mock Graph (Prevent LLM costs)
        # We patch the 'invoke' method on the global 'graph' object in main.py
        with patch("app.main.graph.invoke") as mock_graph:
            # Mock the return value structure of LangGraph
            mock_graph.return_value = {
                "messages": [
                    HumanMessage(content="Hello"),
                    AIMessage(content="I am a test robot")
                ]
            }
            
            # 3. Call the API
            response = await client.post("/chat", json={"message": "Hello"})
            
            # 4. Verify
            assert response.status_code == 200
            data = response.json()
            assert data["response"] == "I am a test robot"
            assert data["user_id"] == "test_user_123"
    finally:
        # Clean up dependency override
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_chat_endpoint_unauthorized(client):
    """Test that requests without auth token are rejected."""
    # No dependency override, so auth should be required
    response = await client.post("/chat", json={"message": "Hello"})
    
    # Should return 401 Unauthorized (HTTPBearer returns 401 when no token)
    assert response.status_code == 401

