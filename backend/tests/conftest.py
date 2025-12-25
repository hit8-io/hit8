"""
Test configuration and fixtures.
"""
import pytest
import pytest_asyncio
import os
from unittest.mock import MagicMock
from httpx import AsyncClient, ASGITransport
from typing import AsyncGenerator

# 1. SET FAKE ENV VARS (Must happen at module import time, before any app imports)
# Set these immediately when conftest is imported, before any fixtures run
os.environ.setdefault("VERTEX_HIT8_POC_IAM_GSERVICEACCOUNT_COM", '{"project_id": "mock", "type": "service_account"}')
os.environ.setdefault("VERTEX_AI_MODEL_NAME", "mock-model")
os.environ.setdefault("GCP_PROJECT", "mock-project")
os.environ.setdefault("GOOGLE_IDENTITY_PLATFORM_DOMAIN", "mock-domain")
os.environ.setdefault("CORS_ALLOW_ORIGINS", '["*"]')


@pytest.fixture(scope="session", autouse=True)
def mock_env():
    """Ensure fake environment variables are set."""
    # These are already set at module level, but this fixture ensures they persist
    os.environ["VERTEX_HIT8_POC_IAM_GSERVICEACCOUNT_COM"] = '{"project_id": "mock", "type": "service_account"}'
    os.environ["VERTEX_AI_MODEL_NAME"] = "mock-model"
    os.environ["GCP_PROJECT"] = "mock-project"
    os.environ["GOOGLE_IDENTITY_PLATFORM_DOMAIN"] = "mock-domain"
    os.environ["CORS_ALLOW_ORIGINS"] = '["*"]'
    yield


# 2. MOCK FIREBASE (Prevent real connection attempts)
@pytest.fixture(scope="session", autouse=True)
def mock_firebase(mock_env):
    """Mock firebase so we don't need real creds."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("firebase_admin.initialize_app", MagicMock())
        mp.setattr("firebase_admin.credentials.Certificate", MagicMock())
        mp.setattr("firebase_admin.auth.verify_id_token", MagicMock())
        yield


# 3. ASYNC CLIENT (For making API requests)
@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client for testing the FastAPI app."""
    # Import app inside fixture to ensure env vars are set first
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

