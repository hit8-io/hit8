# LLM Rate Limiting and Token Handling

## Core Problem

The application experienced multiple issues with LLM calls timing out, rate limits being exceeded, and frontend stream timeouts during report generation.

### Symptoms

1. **429 Rate Limit Errors**: Gemini Pro models have a strict 5 RPM (requests per minute) limit, causing `litellm.exceptions.RateLimitError` when exceeded
2. **Frontend Timeouts**: "The request took too long to complete" errors when LLM calls exceeded the frontend inactivity timeout
3. **Backend Timeouts**: `llm_call_timeout` and `analyst_node_timeout` errors when LLM calls exceeded their configured timeout
4. **Infinite Loops**: Potential for agents to get stuck in tool-calling loops, running indefinitely

### Root Causes

1. **Custom rate limiting was unreliable**: The previous `TokenRateLimiter` and `aiolimiter.AsyncLimiter` implementations didn't properly coordinate with LiteLLM's internal rate limiting
2. **Overly conservative timeout calculations**: Timeout formula used 15ms per input token and 50ms per output token, resulting in unnecessarily long timeouts (e.g., 13+ minutes for 20k tokens)
3. **Keepalive only triggered on events**: During long LLM calls with no streaming events, the frontend could timeout due to inactivity
4. **No recursion limit**: Graphs could run indefinitely if an agent got stuck in a loop
5. **Excessive post-chapter waits**: 120-second waits after each chapter were redundant with rate limiting

## Solutions Implemented

### 1. LiteLLM Router Migration

Migrated from custom rate limiting to LiteLLM Router for centralized LLM management.

**File**: `backend/app/llm_router.py`

- Configured model-specific TPM/RPM quotas
- Automatic retry handling with cooldown
- Unified interface for all Vertex AI and Ollama models

### 2. Application-Level Pro Model Rate Limiter

Added strict 12-second minimum interval between Pro model requests.

**File**: `backend/app/flows/common.py`

```python
_PRO_MODEL_MIN_INTERVAL_SECONDS = 12.0  # 5 RPM = 60/5 = 12 seconds

async def _wait_for_pro_model_rate_limit(model_name: str | None) -> None:
    """Enforce 12 seconds between requests for Pro models."""
    # Only applies to gemini-2.5-pro and gemini-3-pro-preview
```

### 3. Realistic Timeout Calculation

Updated dynamic timeout formula with realistic Gemini performance estimates.

**File**: `backend/app/flows/common.py`

| Parameter | Old Value | New Value |
|-----------|-----------|-----------|
| Input processing | 15ms/token | 2ms/token |
| Output generation | 50ms/token | 15ms/token |
| Base timeout | 120s | 60s |
| Buffer | 180s | 60s |
| Safety margin | None | 2x multiplier |
| Maximum cap | 1 hour | 30 minutes |
| Minimum | 5 minutes | 2 minutes |

**Example calculations**:
- 20k tokens: ~8 minutes timeout (was ~13 minutes)
- 132k tokens: ~26 minutes timeout (was ~60 minutes)

### 4. Graph Recursion Limit

Added recursion limit to prevent infinite agent loops.

**File**: `backend/app/constants.py`
```python
"GRAPH_RECURSION_LIMIT": 50  # Maximum graph steps
```

Applied to all graph invocations in chat and report routes.

### 5. Frontend Timeout Adjustments

Increased frontend timeouts to accommodate long-running operations.

**File**: `frontend/src/constants/index.ts`

| Timeout | Old Value | New Value |
|---------|-----------|-----------|
| `STREAM_TIMEOUT` | 30 minutes | 2 hours |
| `STREAM_INACTIVITY_TIMEOUT` | 10 minutes | 20 minutes |

### 6. Backend Keepalive Interval

Reduced keepalive interval to prevent frontend inactivity timeouts.

**File**: `backend/app/api/streaming/async_events.py`

```python
REPORT_KEEPALIVE_INTERVAL = 30.0  # Was 60 seconds
```

### 7. Removed Redundant Waits

Removed 120-second waits after each chapter that were redundant with rate limiting.

**File**: `backend/app/flows/opgroeien/poc/report/nodes.py`

Removed three instances of `await asyncio.sleep(120)` after chapter completion/failure.

## Current Configuration

### Rate Limits (LiteLLM Router)

| Model | TPM | RPM | Timeout |
|-------|-----|-----|---------|
| gemini-2.5-pro | 250,000 | 5 | 600s |
| gemini-2.5-flash | 5,000,000 | 60 | default |
| gemini-2.0-flash-lite | 5,000,000 | 60 | default |
| gemini-3-pro-preview | 250,000 | 5 | 1200s |
| gemini-3-flash-preview | 5,000,000 | 10 | default |

### Concurrency Limits

| Setting | Value | Description |
|---------|-------|-------------|
| `REPORT_MAX_PARALLEL_WORKERS` | 1 | Chapters processed sequentially |
| `REPORT_LLM_CONCURRENCY` | 1 | One LLM call at a time |
| `REPORT_CONSULT_LLM_CONCURRENCY` | 2 | Nested chat graphs |
| `ANALYST_AGENT_MAX_ITERATIONS` | 30 | ReAct agent loop limit |
| `GRAPH_RECURSION_LIMIT` | 50 | Main graph step limit |

## Possible Improvements

### 1. Proactive Keepalive Task

**Problem**: Keepalive only triggers when events arrive. During long LLM calls with no streaming events, the frontend can still timeout.

**Solution**: Add a background task that sends keepalive events independently of the event loop:

```python
async def _keepalive_task(queue: asyncio.Queue, interval: float):
    """Send keepalive events independently of event processing."""
    while True:
        await asyncio.sleep(interval)
        await queue.put({"type": "keepalive"})
```

### 2. Adaptive Rate Limiting

**Problem**: Fixed 12-second interval may be too conservative or aggressive depending on actual API behavior.

**Solution**: Implement adaptive rate limiting that adjusts based on 429 response frequency:
- If no 429s: gradually decrease interval (min 10s)
- If 429s occur: increase interval and apply exponential backoff

### 3. Token-Aware Batching

**Problem**: Large chapters with many tokens may still hit TPM limits.

**Solution**: Pre-calculate token usage and batch requests to stay within TPM quota:
- Count tokens before sending
- Queue requests if approaching TPM limit
- Distribute load across time windows

### 4. Model Fallback Strategy

**Problem**: Pro models have strict limits; requests fail when quota exhausted.

**Solution**: Implement automatic fallback to Flash models when Pro quota is exhausted:
```python
model_priority = ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash-lite"]
```

### 5. Request Prioritization

**Problem**: All requests are treated equally, but some are more time-sensitive.

**Solution**: Implement priority queues:
- High priority: User-facing chat responses
- Medium priority: Report chapter generation
- Low priority: Background tasks

### 6. Observability Improvements

**Problem**: Difficult to debug timeout issues without detailed metrics.

**Solution**: Add comprehensive metrics:
- Time spent waiting for rate limiter
- Actual LLM call duration
- Time to first token (TTFT)
- Queue depth and wait times
- Per-model success/failure rates

### 7. Circuit Breaker Pattern

**Problem**: Repeated failures to the same model waste resources.

**Solution**: Implement circuit breaker that temporarily disables a model after consecutive failures:
```python
class ModelCircuitBreaker:
    def __init__(self, failure_threshold=5, reset_timeout=300):
        self.failures = 0
        self.state = "closed"  # closed, open, half-open
```

## Files Modified

| File | Changes |
|------|---------|
| `backend/app/llm_router.py` | New - LiteLLM Router configuration |
| `backend/app/flows/common.py` | Rate limiter, timeout calculation |
| `backend/app/constants.py` | Recursion limit, concurrency settings |
| `backend/app/api/routes/chat.py` | Added recursion_limit to config |
| `backend/app/api/routes/report.py` | Added recursion_limit to config |
| `backend/app/api/streaming/async_events.py` | Reduced keepalive interval |
| `backend/app/flows/opgroeien/poc/report/nodes.py` | Removed 120s waits |
| `frontend/src/constants/index.ts` | Increased timeouts |

## Deleted Files

| File | Reason |
|------|--------|
| `backend/app/limiter.py` | Replaced by LiteLLM Router |
| `backend/tests/unit/test_rate_limiting.py` | Tests for removed code |
