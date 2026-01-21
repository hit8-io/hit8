# API Reference

## Base URL

**Production**: Configured via `VITE_API_URL` environment variable

**Development**: `http://localhost:8000`

## Authentication

All API endpoints except `/health` and `/version` require authentication via Bearer token.

**Header Format:**
```
Authorization: Bearer <id_token>
```

**Token Source:**
- Obtained from Google Identity Platform (Firebase Auth)
- ID token generated on frontend
- Verified on backend using Firebase Admin SDK

**Error Response (401 Unauthorized):**
```json
{
  "detail": "Not authenticated"
}
```

## Endpoints

### Health Check

**Endpoint**: `GET /health`

**Description**: Health check endpoint for monitoring and load balancer health checks.

**Authentication**: Not required

**Request:**
```http
GET /health HTTP/1.1
Host: api.example.com
```

**Response:**
```json
{
  "status": "healthy"
}
```

**Status Codes:**
- `200 OK`: Service is healthy

**Example:**
```bash
curl http://localhost:8000/health
```

### Chat

**Endpoint**: `POST /chat`

**Description**: Processes user chat messages through LangGraph and streams AI-generated responses as Server-Sent Events (SSE).

**Authentication**: Required (Bearer token)

**Request:**
- **Content-Type**: `multipart/form-data`
- **Form fields**: `message` (required), `thread_id` (optional), `model` (optional), `files` (optional, multiple)
- **Required headers**: `Authorization: Bearer <id_token>`, `X-Org`, `X-Project`

```http
POST /chat HTTP/1.1
Host: api.example.com
Authorization: Bearer <id_token>
X-Org: opgroeien
X-Project: poc
Content-Type: multipart/form-data; boundary=----WebKitFormBoundary

------WebKitFormBoundary
Content-Disposition: form-data; name="message"

Hello, how are you?
------WebKitFormBoundary--
```

**Response:**
- **Content-Type**: `text/event-stream`
- **Body**: SSE stream. Main event types: `graph_start`, `content_chunk`, `state_update`, `tool_start`/`tool_end`, `llm_start`/`llm_end`, `graph_end`, `error`. See [architecture.md](architecture.md) for full event semantics.

**Status Codes:**
- `200 OK`: Stream started successfully
- `401 Unauthorized`: Missing or invalid authentication token
- `403 Forbidden`: User does not have access to the requested org/project
- `422 Unprocessable Entity`: Invalid request (e.g. missing `message` or required headers)
- `500 Internal Server Error`: Server error during processing

**Example (curl):**
```bash
curl -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer <id_token>" \
  -H "X-Org: opgroeien" \
  -H "X-Project: poc" \
  -F "message=Hello" \
  -F "thread_id=optional-uuid"
```

**Error Responses (non-streaming):** 401, 403, 422 return JSON `{"detail": "..."}`. During streaming, `error` events are sent in the SSE stream.

### Other Endpoints

For full request/response schemas and parameters, see the live **OpenAPI** docs: `GET /docs` (Swagger UI) and `GET /openapi.json`.

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check (no auth) |
| `GET /version` | API version (no auth) |
| `GET /config/user` | User config (auth, `X-Org`, `X-Project`) |
| `GET /config/models` | Available models (auth, `X-Org`, `X-Project`) |
| `GET /metadata` | Metadata (auth) |
| `GET /graph/structure` | Graph nodes/edges (auth, `X-Org`, `X-Project`) |
| `GET /graph/state` | Checkpointed state for `thread_id` (auth, `X-Org`, `X-Project`) |
| `GET /history` | User threads (auth, `X-Org`, `X-Project`) |
| `GET /usage/execution/{thread_id}` | Execution metrics (auth) |
| `GET /usage/aggregated` | Aggregated metrics (auth) |
| `GET /usage/executions` | List executions (auth) |
| `POST /report/start`, `GET /report/{thread_id}/status`, etc. | Report flow (auth, `X-Org`, `X-Project`). See OpenAPI for full list. |

### Content Types

**Chat**: `multipart/form-data` (request), `text/event-stream` (response).

**Other JSON endpoints**: `application/json` request/response where applicable. **Character encoding**: UTF-8.

## Error Handling

### Error Response Format

All errors follow a consistent format:

```json
{
  "detail": "Error message or validation details"
}
```

### Error Types

**Authentication Errors (401):**
- Missing `Authorization` header
- Invalid token format
- Expired or invalid ID token
- Token verification failure

**Validation Errors (422):**
- Missing required fields
- Invalid field types
- Invalid field values

**Server Errors (500):**
- Internal application errors
- External service failures (Vertex AI, etc.)
- Unexpected exceptions

### Error Handling in Frontend

**Example (Chat with FormData and SSE):**
```typescript
const form = new FormData()
form.append('message', userMessage.content)
if (threadId) form.append('thread_id', threadId)

const response = await fetch(`${API_URL}/chat`, {
  method: 'POST',
  headers: {
    Authorization: `Bearer ${token}`,
    'X-Org': org,
    'X-Project': project,
  },
  body: form,
})
if (!response.ok) {
  const err = await response.json().catch(() => ({ detail: response.statusText }))
  // handle 401, 403, 422, 500 via err.detail
  return
}
// response.body is a ReadableStream; consume as SSE (EventSource or manual parsing)
```

## Rate Limiting

Currently, the API does not implement rate limiting. Consider implementing rate limiting for production use to prevent abuse.

## CORS Configuration

**Allowed Origins:**
- Production: `https://www.hit8.io`, `https://hit8.io`, `https://hit8.pages.dev`
- Development: `http://localhost:5173`, `http://127.0.0.1:5173`

**Allowed Methods**: All (`*`)

**Allowed Headers**: All (`*`)

**Credentials**: Allowed

## API Versioning

Currently, the API does not use versioning. All endpoints are at the root level.

**Future Considerations:**
- Add version prefix: `/v1/chat`, `/v2/chat`
- Maintain backward compatibility
- Deprecation strategy

## Response Times

**Typical Response Times:**
- Health check: < 100ms
- Chat endpoint: 2-10 seconds (depends on Vertex AI response time)

**Factors Affecting Response Time:**
- Vertex AI model response time
- Network latency
- Cold start (if scaling from zero)
- Request complexity

## Testing the API

### Using curl

**Health Check:**
```bash
curl http://localhost:8000/health
```

**Chat (multipart/form-data, SSE response):**
```bash
curl -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer <id_token>" \
  -H "X-Org: opgroeien" \
  -H "X-Project: poc" \
  -F "message=Hello"
```

### Using HTTPie

**Health Check:**
```bash
http GET http://localhost:8000/health
```

**Chat (form + SSE):**
```bash
http --form POST http://localhost:8000/chat \
  Authorization:"Bearer <id_token>" \
  X-Org:opgroeien \
  X-Project:poc \
  message="Hello"
```

### Using Postman

1. Create new request; set method to `POST`, URL to `http://localhost:8000/chat`
2. Headers: `Authorization: Bearer <id_token>`, `X-Org`, `X-Project`
3. Body: form-data with `message` (and optionally `thread_id`, `model`, `files`)
4. Send request; response is `text/event-stream` (SSE)

## OpenAPI Documentation

FastAPI automatically generates OpenAPI documentation:

**Swagger UI**: `http://localhost:8000/docs`

**ReDoc**: `http://localhost:8000/redoc`

**OpenAPI JSON**: `http://localhost:8000/openapi.json`

**Features:**
- Interactive API documentation
- Try-it-out functionality
- Request/response schemas
- Authentication testing























