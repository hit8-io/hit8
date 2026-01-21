# Testing

## Testing Strategy

Hit8 uses **pytest** for backend testing with a focus on unit tests and integration tests.

### Test Structure

```
backend/tests/
├── conftest.py           # Test configuration and fixtures
├── unit/
│   ├── test_async_events.py
│   ├── test_config.py
│   ├── test_document_utils.py
│   ├── test_file_processing.py
│   ├── test_graph.py
│   ├── test_graph_agent.py
│   ├── test_prompt_loader.py
│   └── test_tools.py
└── integration/
    ├── test_chat_api.py  # Chat API
    └── test_file_upload.py
```

## Test Types

### Unit Tests

**Location**: `backend/tests/unit/`

**Purpose**: Test individual components in isolation

**Example**: [`test_graph.py`](backend/tests/unit/test_graph.py)
- Tests LangGraph node functions
- Mocks external dependencies (Vertex AI, credentials)
- Validates state transformations

### Integration Tests

**Location**: `backend/tests/integration/`

**Purpose**: Test API endpoints with full request/response cycle

**Example**: [`test_chat_api.py`](backend/tests/integration/test_chat_api.py)
- Tests complete API request flow
- Mocks authentication and LangGraph
- Validates response formats

## Test Configuration

### conftest.py

**File**: [`backend/tests/conftest.py`](backend/tests/conftest.py)

**Key Features:**

1. **Environment Variable Setup:**
   ```python
   os.environ.setdefault("VERTEX_HIT8_POC_IAM_GSERVICEACCOUNT_COM", 
                        '{"project_id": "mock", "type": "service_account"}')
   os.environ.setdefault("GCP_PROJECT", "mock-project")
   os.environ.setdefault("GOOGLE_IDENTITY_PLATFORM_DOMAIN", "mock-domain")
   ```

2. **Firebase Mocking:**
   ```python
   @pytest.fixture(scope="session", autouse=True)
   def mock_firebase(mock_env):
       """Mock firebase so we don't need real creds."""
       with pytest.MonkeyPatch.context() as mp:
           mp.setattr("firebase_admin.initialize_app", MagicMock())
           mp.setattr("firebase_admin.credentials.Certificate", MagicMock())
           mp.setattr("firebase_admin.auth.verify_id_token", MagicMock())
           yield
   ```

3. **Async Client Fixture:**
   ```python
   @pytest_asyncio.fixture
   async def client() -> AsyncGenerator[AsyncClient, None]:
       """Create an async HTTP client for testing the FastAPI app."""
       from app.main import app
       transport = ASGITransport(app=app)
       async with AsyncClient(transport=transport, base_url="http://test") as ac:
           yield ac
   ```

**Configuration Order:**
1. Set fake environment variables (before app imports)
2. Mock Firebase Admin SDK (prevent real connections)
3. Create async HTTP client (for API requests)

## Running Tests

### Basic Commands

**Run all tests:**
```bash
cd backend
pytest
```

**Run specific test file:**
```bash
pytest tests/unit/test_graph.py
pytest tests/integration/test_chat_api.py
```

**Run with verbose output:**
```bash
pytest -v
```

**Run with output:**
```bash
pytest -s
```

### Test Coverage

**Install coverage tool:**
```bash
pip install pytest-cov
```

**Run with coverage:**
```bash
pytest --cov=app --cov-report=html
```

**View coverage report:**
- HTML report: `htmlcov/index.html`
- Terminal report: `--cov-report=term`

### Test Markers

**Async tests:**
```python
@pytest.mark.asyncio
async def test_chat_endpoint_success(client):
    # Test code
```

**Run only async tests:**
```bash
pytest -m asyncio
```

## Mocking Strategy

### Firebase Admin Mocking

**Purpose**: Prevent real Firebase connections during tests

**Implementation:**
```python
@pytest.fixture(scope="session", autouse=True)
def mock_firebase(mock_env):
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("firebase_admin.initialize_app", MagicMock())
        mp.setattr("firebase_admin.credentials.Certificate", MagicMock())
        mp.setattr("firebase_admin.auth.verify_id_token", MagicMock())
        yield
```

**Benefits:**
- No real Firebase credentials needed
- Faster test execution
- Isolated test environment

### LangGraph Mocking

**Purpose**: Prevent real LLM API calls (avoid costs and latency)

**Implementation:** The chat and other routes obtain a graph via `app.api.graph_manager.get_graph(org, project)`. Mock at that layer or at the graph’s `ainvoke` / `astream_events`:

```python
# Option 1: Mock get_graph to return a graph-like object with ainvoke/astream_events
with patch("app.api.graph_manager.get_graph") as mock_get_graph:
    mock_graph = MagicMock()
    mock_graph.ainvoke.return_value = {"messages": [HumanMessage(content="Hi"), AIMessage(content="Response")]}
    mock_get_graph.return_value = mock_graph
    # Test code

# Option 2: If the route uses a module-level graph, patch where it is used (e.g. the route or graph_manager)
```

**Benefits:**
- No Vertex AI API costs
- Faster test execution
- Predictable test results

### Authentication Mocking

**Purpose**: Bypass token verification in tests

**Implementation:** Override `verify_google_token` from `app.auth`:

```python
from app.auth import verify_google_token

async def mock_verify_token():
    return {"sub": "test_user_123"}

app.dependency_overrides[verify_google_token] = mock_verify_token
```

**Cleanup:**
```python
try:
    # Test code
finally:
    app.dependency_overrides.clear()
```

**Benefits:**
- No real authentication needed
- Test with known user IDs
- Isolated test environment

### Environment Variable Setup

**Purpose**: Provide mock configuration for tests

**Implementation:**
```python
os.environ.setdefault("VERTEX_HIT8_POC_IAM_GSERVICEACCOUNT_COM", 
                     '{"project_id": "mock", "type": "service_account"}')
os.environ.setdefault("GCP_PROJECT", "mock-project")
os.environ.setdefault("GOOGLE_IDENTITY_PLATFORM_DOMAIN", "mock-domain")
```

**Timing:**
- Set at module import time (before app imports)
- Ensures settings are available when app initializes

## Test Examples

### Unit Test Example

**File**: `backend/tests/unit/test_graph.py` or `test_graph_agent.py`

Unit tests typically patch the flow module or the model/credentials at the point of use (e.g. `app.flows.opgroeien.poc.chat.graph` or the specific node’s model/LLM). Example pattern:

```python
# Patch the model or credentials in the flow module where they are used
with patch("app.flows.opgroeien.poc.chat.graph.ChatGoogleGenerativeAI") as MockModel:
    mock_instance = MockModel.return_value
    mock_instance.invoke.return_value = AIMessage(content="Mocked AI Response")
    # Run node or graph and assert on state
```

**Key Points:**
- Mock external dependencies (credentials, Vertex AI) in the flow or node under test
- Tests state transformation
- Validates response format

### Integration Test Example

**File**: `backend/tests/integration/test_chat_api.py`

```python
from app.api import app
from app.auth import verify_google_token

@pytest.mark.asyncio
async def test_chat_endpoint_success(client):
    async def mock_verify_token():
        return {"sub": "test_user_123", "email": "t@ex.com"}

    app.dependency_overrides[verify_google_token] = mock_verify_token
    try:
        with patch("app.api.graph_manager.get_graph") as mock_get:
            mock_graph = MagicMock()
            # Chat uses astream_events; ainvoke or astream_events must be mocked as needed
            mock_graph.ainvoke.return_value = {"messages": [HumanMessage(content="Hi"), AIMessage(content="OK")]}
            mock_get.return_value = mock_graph
            # Chat API uses FormData and X-Org, X-Project; response is SSE. Adapt to current route contract.
            response = await client.post("/chat", data={"message": "Hi"}, headers={"X-Org": "opgroeien", "X-Project": "poc"})
            assert response.status_code == 200
    finally:
        app.dependency_overrides.clear()
```

**Key Points:**
- Override `verify_google_token` from `app.auth`
- Mock `app.api.graph_manager.get_graph` (or the graph’s `astream_events`/`ainvoke`) to avoid LLM calls
- Chat uses `multipart/form-data`, `X-Org`, `X-Project`, and SSE (see [api-reference](api-reference.md)); adjust request/assertions to the current contract

### Unauthorized Test Example

```python
@pytest.mark.asyncio
async def test_chat_endpoint_unauthorized(client):
    """Test that requests without auth token are rejected."""
    # No dependency override, so auth should be required
    response = await client.post("/chat", json={"message": "Hello"})
    
    # Should return 401 Unauthorized (HTTPBearer returns 401 when no token)
    assert response.status_code == 401
```

**Key Points:**
- Tests authentication requirement
- No token provided
- Validates 401 response

## Test Best Practices

### 1. Isolate Tests

- Each test should be independent
- Use fixtures for setup/teardown
- Clean up mocks and overrides

### 2. Mock External Dependencies

- Mock Firebase Admin SDK
- Mock Vertex AI API calls
- Mock external services

### 3. Test Edge Cases

- Missing authentication
- Invalid requests
- Error conditions

### 4. Use Descriptive Names

- Test names should describe what they test
- Use docstrings for complex tests
- Group related tests in classes

### 5. Keep Tests Fast

- Mock external calls
- Use in-memory fixtures
- Avoid real network requests

## Continuous Integration

### GitHub Actions (Future)

Tests can be integrated into CI/CD pipeline:

```yaml
- name: Run tests
  run: |
    cd backend
    pytest --cov=app --cov-report=xml
```

### Pre-commit Hooks (Recommended)

Run tests before committing:

```bash
# Install pre-commit
pip install pre-commit

# Setup hook
pre-commit install
```

## Troubleshooting Tests

### Common Issues

**1. Firebase Initialization Errors:**
- Ensure `mock_firebase` fixture is applied
- Check that Firebase is mocked before app import

**2. Missing Environment Variables:**
- Verify `conftest.py` sets all required variables
- Check variable names match settings

**3. Async Test Failures:**
- Ensure `@pytest.mark.asyncio` decorator
- Use `pytest-asyncio` for async support

**4. Import Errors:**
- Check Python path
- Verify dependencies installed
- Run from correct directory

### Debugging Tests

**Run with verbose output:**
```bash
pytest -vv
```

**Run with print statements:**
```bash
pytest -s
```

**Run specific test:**
```bash
pytest tests/integration/test_chat_api.py::test_chat_endpoint_success
```

**Use debugger:**
```python
import pdb; pdb.set_trace()
```























