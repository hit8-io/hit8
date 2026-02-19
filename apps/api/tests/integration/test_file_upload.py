"""
Integration tests for file upload functionality.
"""
import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from io import BytesIO


@pytest.mark.asyncio
async def test_chat_endpoint_with_file_upload(client):
    """Test chat endpoint with file upload."""
    from app.main import app
    from app.auth import verify_google_token
    
    async def mock_verify_token():
        return {
            "sub": "test_user_123",
            "email": "test@example.com",
            "name": "Test User",
        }
    
    app.dependency_overrides[verify_google_token] = mock_verify_token
    
    try:
        # Mock user access validation
        with patch("app.api.routes.chat.validate_user_access", return_value=True), \
             patch("app.api.routes.chat.process_uploaded_files") as mock_process, \
             patch("app.api.streaming.async_events.process_async_stream_events") as mock_stream:
            
            # Mock file processing to return document content
            mock_process.return_value = "## test.docx\n\n# Test Document\n\nContent"
            
            # Mock streaming - async generator that yields SSE strings only
            async def mock_stream_gen():
                yield 'data: {"type": "graph_end", "thread_id": "test", "response": "Test response"}\n\n'
            mock_stream.return_value = mock_stream_gen()
            
            # Create test file
            file_content = b"fake docx content"
            files = {
                "files": ("test.docx", BytesIO(file_content), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            }
            
            # Get API token from environment (injected by Doppler)
            api_token = os.getenv("API_TOKEN", "test-token")
            
            # Call the API with multipart form data
            response = await client.post(
                "/chat",
                data={
                    "message": "Hello",
                    "thread_id": "test_thread_123"
                },
                files=files,
                headers={
                    "X-Org": "opgroeien",
                    "X-Project": "poc",
                    "X-Source-Token": api_token,
                    "Authorization": "Bearer fake-token"
                }
            )
            
            # Verify
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
            mock_process.assert_called_once()
            
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_chat_endpoint_without_files(client):
    """Test chat endpoint without files (backward compatibility)."""
    from app.main import app
    from app.auth import verify_google_token
    
    async def mock_verify_token():
        return {
            "sub": "test_user_123",
            "email": "test@example.com",
        }
    
    app.dependency_overrides[verify_google_token] = mock_verify_token
    
    try:
        # Mock user access validation
        with patch("app.api.routes.chat.validate_user_access", return_value=True), \
             patch("app.api.streaming.async_events.process_async_stream_events") as mock_stream:
            
            # Mock streaming - async generator that yields SSE strings only
            async def mock_stream_gen():
                yield 'data: {"type": "graph_end", "thread_id": "test", "response": "Test response"}\n\n'
            mock_stream.return_value = mock_stream_gen()
            
            # Get API token from environment (injected by Doppler)
            api_token = os.getenv("API_TOKEN", "test-token")
            
            # Call without files
            response = await client.post(
                "/chat",
                data={
                    "message": "Hello",
                },
                headers={
                    "X-Org": "opgroeien",
                    "X-Project": "poc",
                    "X-Source-Token": api_token,
                    "Authorization": "Bearer fake-token"
                }
            )
            
            assert response.status_code == 200
            
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_chat_endpoint_invalid_file_type(client):
    """Test chat endpoint with invalid file type."""
    from app.main import app
    from app.auth import verify_google_token
    
    async def mock_verify_token():
        return {
            "sub": "test_user_123",
            "email": "test@example.com",
        }
    
    app.dependency_overrides[verify_google_token] = mock_verify_token
    
    try:
        # Mock user access validation
        with patch("app.api.routes.chat.validate_user_access", return_value=True):
            file_content = b"fake exe content"
            files = {
                "files": ("test.exe", BytesIO(file_content), "application/x-msdownload")
            }
            
            # Get API token from environment (injected by Doppler)
            api_token = os.getenv("API_TOKEN", "test-token")
            
            response = await client.post(
                "/chat",
                data={
                    "message": "Hello",
                },
                files=files,
                headers={
                    "X-Org": "opgroeien",
                    "X-Project": "poc",
                    "X-Source-Token": api_token,
                    "Authorization": "Bearer fake-token"
                }
            )
            
            # When all files fail validation, we return 500 with summary
            assert response.status_code == 500
            assert "failed to process all files" in response.text.lower()
    
    finally:
        app.dependency_overrides.clear()
