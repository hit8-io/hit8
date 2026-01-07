# API Reference

## Base URL

**Production**: Configured via `VITE_API_URL` environment variable

**Development**: `http://localhost:8000`

## Authentication

All API endpoints (except `/health`) require authentication via Bearer token.

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

**Description**: Processes user chat messages through LangGraph and returns AI-generated responses.

**Authentication**: Required (Bearer token)

**Request:**
```http
POST /chat HTTP/1.1
Host: api.example.com
Authorization: Bearer <id_token>
Content-Type: application/json

{
  "message": "Hello, how are you?"
}
```

**Request Body Schema:**
```typescript
interface ChatRequest {
  message: string;  // User's chat message
}
```

**Response:**
```json
{
  "response": "Hello! I'm doing well, thank you for asking. How can I help you today?",
  "user_id": "user_123456789"
}
```

**Response Schema:**
```typescript
interface ChatResponse {
  response: string;  // AI-generated response
  user_id: string;   // User ID from authenticated token
}
```

**Status Codes:**
- `200 OK`: Request processed successfully
- `401 Unauthorized`: Missing or invalid authentication token
- `422 Unvalidation Error`: Invalid request body
- `500 Internal Server Error`: Server error during processing

**Example:**
```bash
curl -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer <id_token>" \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello, how are you?"}'
```

**Error Responses:**

**401 Unauthorized (Missing Token):**
```json
{
  "detail": "Not authenticated"
}
```

**401 Unauthorized (Invalid Token):**
```json
{
  "detail": "Could not validate credentials"
}
```

**422 Unprocessable Entity (Invalid Request):**
```json
{
  "detail": [
    {
      "loc": ["body", "message"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

**500 Internal Server Error:**
```json
{
  "detail": "Internal server error"
}
```

## Request/Response Formats

### Pydantic Models

**Request Model**: `ChatRequest`
- Defined in [`backend/app/main.py`](backend/app/main.py)
- Validates request body structure
- Ensures `message` field is present and is a string

**Response Model**: `ChatResponse`
- Defined in [`backend/app/main.py`](backend/app/main.py)
- Validates response structure
- Ensures `response` and `user_id` fields are present

### Content Types

**Request Content-Type**: `application/json`

**Response Content-Type**: `application/json`

**Character Encoding**: UTF-8

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

**Example Error Handling:**
```typescript
try {
  const response = await axios.post(
    `${API_URL}/chat`,
    { message: userMessage.content },
    {
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    }
  )
  // Handle success
} catch (error) {
  if (error.response?.status === 401) {
    // Handle authentication error
  } else if (error.response?.status === 422) {
    // Handle validation error
  } else {
    // Handle other errors
  }
}
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

**Chat (with authentication):**
```bash
curl -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer <id_token>" \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello"}'
```

### Using HTTPie

**Health Check:**
```bash
http GET http://localhost:8000/health
```

**Chat:**
```bash
http POST http://localhost:8000/chat \
  Authorization:"Bearer <id_token>" \
  message="Hello"
```

### Using Postman

1. Create new request
2. Set method to `POST`
3. Set URL to `http://localhost:8000/chat`
4. Add header: `Authorization: Bearer <id_token>`
5. Set body to JSON: `{"message": "Hello"}`
6. Send request

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






















