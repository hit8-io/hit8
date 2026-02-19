"""
Test configuration and fixtures.

Note: Tests should be run with Doppler to inject secrets:
    doppler run --project hit8 --config dev -- pytest ...

Doppler will inject all required secrets as environment variables.
No defaults are provided - all secrets must come from Doppler.
"""
import pytest
import pytest_asyncio
from unittest.mock import MagicMock
from httpx import AsyncClient, ASGITransport
from typing import AsyncGenerator

# No environment variable defaults - all secrets must be provided by Doppler
# Run tests with: doppler run --project hit8 --config dev -- pytest ...


# 2. MOCK FIREBASE (Prevent real connection attempts)
@pytest.fixture(scope="session", autouse=True)
def mock_firebase():
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

