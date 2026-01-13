"""
In-memory observability metrics storage for LLM, embedding, and Bright Data usage tracking.
"""
from __future__ import annotations

import contextvars
import threading
import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth import verify_google_token

# Context variable to track current thread_id during execution
_current_thread_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_thread_id", default=None)

logger = None  # Will be initialized when structlog is available


class LLMUsage(BaseModel):
    """LLM usage metrics for a single call."""
    model: str
    config: dict[str, Any] = Field(default_factory=dict)  # temperature, thinking_level, etc.
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int | None = None
    ttft_ms: float | None = None  # Time to first token in milliseconds
    duration_ms: float
    timestamp: datetime


class EmbeddingUsage(BaseModel):
    """Embedding model usage metrics for a single call."""
    model: str
    input_tokens: int = 0
    output_tokens: int = 0  # Usually 0 for embeddings
    duration_ms: float
    timestamp: datetime


class BrightDataUsage(BaseModel):
    """Bright Data usage metrics aggregated per execution."""
    call_count: int = 0
    total_duration_ms: float = 0.0
    total_cost: float | None = None
    total_bytes: int = 0  # Total bytes transferred


class ExecutionMetrics(BaseModel):
    """Metrics for a single flow execution (thread_id)."""
    thread_id: str
    start_time: datetime
    end_time: datetime | None = None
    llm_calls: list[LLMUsage] = Field(default_factory=list)
    embedding_calls: list[EmbeddingUsage] = Field(default_factory=list)
    brightdata_calls: BrightDataUsage = Field(default_factory=BrightDataUsage)


class ModelUsageStats(BaseModel):
    """Usage statistics for a specific model."""
    call_count: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_thinking_tokens: int = 0
    total_duration_ms: float = 0.0


class LLMAggregatedMetrics(BaseModel):
    """Aggregated LLM usage metrics."""
    total_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_thinking_tokens: int = 0
    total_duration_ms: float = 0.0
    avg_ttft_ms: float | None = None
    by_model: dict[str, ModelUsageStats] = Field(default_factory=dict)


class EmbeddingAggregatedMetrics(BaseModel):
    """Aggregated embedding usage metrics."""
    total_calls: int = 0
    total_input_tokens: int = 0
    total_duration_ms: float = 0.0
    by_model: dict[str, ModelUsageStats] = Field(default_factory=dict)


class BrightDataAggregatedMetrics(BaseModel):
    """Aggregated Bright Data usage metrics."""
    total_calls: int = 0
    total_duration_ms: float = 0.0
    total_cost: float | None = None
    total_bytes: int = 0  # Total bytes transferred


class AggregatedMetrics(BaseModel):
    """Aggregated metrics across all executions."""
    total_executions: int = 0
    llm: LLMAggregatedMetrics = Field(default_factory=LLMAggregatedMetrics)
    embeddings: EmbeddingAggregatedMetrics = Field(default_factory=EmbeddingAggregatedMetrics)
    brightdata: BrightDataAggregatedMetrics = Field(default_factory=BrightDataAggregatedMetrics)


# Thread-safe storage (initialized after model definitions)
_execution_metrics: dict[str, ExecutionMetrics] = {}
_execution_metrics_lock = threading.Lock()

_aggregated_metrics = AggregatedMetrics()
_aggregated_metrics_lock = threading.Lock()

# Track LLM call start times for TTFT calculation
_llm_call_starts: dict[str, dict[str, float]] = {}  # thread_id -> {call_id: start_time}
_llm_call_starts_lock = threading.Lock()

# Track run_id to call_id mapping
_run_id_to_call_id: dict[str, dict[str, str]] = {}  # thread_id -> {run_id: call_id}
_run_id_to_call_id_lock = threading.Lock()

# Track first token arrival times for TTFT
_first_token_times: dict[str, dict[str, float]] = {}  # thread_id -> {call_id: first_token_time}
_first_token_times_lock = threading.Lock()

# Track last thread_id that had an execution to detect thread_id changes
_last_execution_thread_id: str | None = None
_last_execution_thread_id_lock = threading.Lock()


def _get_logger():
    """Lazy import of logger to avoid circular dependencies."""
    global logger
    if logger is None:
        import structlog
        logger = structlog.get_logger(__name__)
    return logger


def initialize_execution(thread_id: str) -> None:
    """Initialize metrics tracking for a new flow execution.
    
    Metrics accumulate within the same thread_id across multiple messages.
    Metrics are cleared when thread_id changes (new chat button creates new thread_id).
    
    Args:
        thread_id: Unique identifier for the flow execution
    """
    global _last_execution_thread_id
    _current_thread_id.set(thread_id)
    
    # Check if thread_id has changed - if so, clear old thread_id's metrics
    with _last_execution_thread_id_lock:
        thread_id_changed = _last_execution_thread_id is not None and _last_execution_thread_id != thread_id
        if thread_id_changed and _last_execution_thread_id:
            clear_execution_metrics(_last_execution_thread_id)
        _last_execution_thread_id = thread_id
    
    with _execution_metrics_lock:
        if thread_id not in _execution_metrics:
            _execution_metrics[thread_id] = ExecutionMetrics(
                thread_id=thread_id,
                start_time=datetime.utcnow(),
            )
            _get_logger().debug(
                "execution_metrics_initialized",
                thread_id=thread_id,
            )


def finalize_execution(thread_id: str) -> None:
    """Mark a flow execution as completed.
    
    Args:
        thread_id: Unique identifier for the flow execution
    """
    with _execution_metrics_lock:
        if thread_id in _execution_metrics:
            _execution_metrics[thread_id].end_time = datetime.utcnow()
            _get_logger().debug(
                "execution_metrics_finalized",
                thread_id=thread_id,
            )


def record_llm_start(thread_id: str, call_id: str, model: str, config: dict[str, Any] | None = None, run_id: str | None = None) -> None:
    """Record the start of an LLM call for timing purposes.
    
    Args:
        thread_id: Flow execution identifier
        call_id: Unique identifier for this LLM call
        model: Model name
        config: Model configuration (temperature, thinking_level, etc.)
        run_id: LangGraph run ID (for mapping stream events to calls)
    """
    start_time = time.perf_counter()
    with _llm_call_starts_lock:
        if thread_id not in _llm_call_starts:
            _llm_call_starts[thread_id] = {}
        _llm_call_starts[thread_id][call_id] = start_time
    
    # Store run_id mapping if provided
    if run_id:
        with _run_id_to_call_id_lock:
            if thread_id not in _run_id_to_call_id:
                _run_id_to_call_id[thread_id] = {}
            _run_id_to_call_id[thread_id][run_id] = call_id


def record_first_token(thread_id: str, call_id: str | None = None, run_id: str | None = None) -> None:
    """Record when the first token arrives for TTFT calculation.
    
    Args:
        thread_id: Flow execution identifier
        call_id: Unique identifier for this LLM call (if known directly)
        run_id: LangGraph run ID (will be mapped to call_id if call_id not provided)
    """
    # Resolve call_id from run_id if needed
    if not call_id and run_id:
        with _run_id_to_call_id_lock:
            call_id = _run_id_to_call_id.get(thread_id, {}).get(run_id)
    
    if not call_id:
        # Can't track without call_id
        return
    
    first_token_time = time.perf_counter()
    with _first_token_times_lock:
        if thread_id not in _first_token_times:
            _first_token_times[thread_id] = {}
        # Only record the first time
        if call_id not in _first_token_times[thread_id]:
            _first_token_times[thread_id][call_id] = first_token_time


def extract_token_usage(response: Any) -> tuple[int, int, int | None]:
    """Extract token usage from LLM response object.
    
    Handles various response formats:
    - LangChain AIMessage with usage_metadata attribute
    - Response with response_metadata containing token_usage or usage_metadata
    - Dict or object with prompt_tokens/completion_tokens or input_tokens/output_tokens
    
    Args:
        response: LLM response object (AIMessage, dict, or object with metadata)
        
    Returns:
        Tuple of (input_tokens, output_tokens, thinking_tokens)
    """
    token_usage = None
    
    # Try usage_metadata attribute first
    if hasattr(response, "usage_metadata"):
        try:
            token_usage = response.usage_metadata
        except Exception:
            pass
    
    # Try response_metadata if usage_metadata not found
    if not token_usage and hasattr(response, "response_metadata"):
        try:
            rm = response.response_metadata
            if rm:
                if hasattr(rm, "get"):
                    token_usage = rm.get("token_usage") or rm.get("usage_metadata")
                elif hasattr(rm, "token_usage"):
                    token_usage = rm.token_usage
                elif hasattr(rm, "usage_metadata"):
                    token_usage = rm.usage_metadata
        except Exception:
            pass
    
    # Extract token counts
    input_tokens = 0
    output_tokens = 0
    thinking_tokens = None
    
    if token_usage:
        if isinstance(token_usage, dict):
            input_tokens = token_usage.get("prompt_tokens", token_usage.get("input_tokens", 0))
            output_tokens = token_usage.get("completion_tokens", token_usage.get("output_tokens", 0))
            thinking_tokens = token_usage.get("thinking_tokens", token_usage.get("cached_tokens"))
        elif hasattr(token_usage, "prompt_tokens") or hasattr(token_usage, "input_tokens"):
            input_tokens = getattr(token_usage, "prompt_tokens", 0) or getattr(token_usage, "input_tokens", 0)
            output_tokens = getattr(token_usage, "completion_tokens", 0) or getattr(token_usage, "output_tokens", 0)
            thinking_tokens = getattr(token_usage, "thinking_tokens", None)
    
    return (input_tokens, output_tokens, thinking_tokens)


def record_llm_usage(
    thread_id: str,
    call_id: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    thinking_tokens: int | None = None,
    config: dict[str, Any] | None = None,
) -> None:
    """Record LLM usage metrics for a completed call.
    
    Args:
        thread_id: Flow execution identifier
        call_id: Unique identifier for this LLM call
        model: Model name
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        thinking_tokens: Number of thinking tokens (if available)
        config: Model configuration dict
    """
    # Calculate duration
    duration_ms = 0.0
    ttft_ms = None
    
    with _llm_call_starts_lock:
        start_time = _llm_call_starts.get(thread_id, {}).get(call_id)
        if start_time:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
    
    # Calculate TTFT if first token was recorded
    with _first_token_times_lock:
        first_token_time = _first_token_times.get(thread_id, {}).get(call_id)
        if first_token_time and start_time:
            ttft_ms = (first_token_time - start_time) * 1000.0
    
    usage = LLMUsage(
        model=model,
        config=config or {},
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        thinking_tokens=thinking_tokens,
        ttft_ms=ttft_ms,
        duration_ms=duration_ms,
        timestamp=datetime.utcnow(),
    )
    
    # Record per execution
    with _execution_metrics_lock:
        if thread_id not in _execution_metrics:
            initialize_execution(thread_id)
        _execution_metrics[thread_id].llm_calls.append(usage)
    
    # Update aggregated metrics
    with _aggregated_metrics_lock:
        _aggregated_metrics.llm.total_calls += 1
        _aggregated_metrics.llm.total_input_tokens += input_tokens
        _aggregated_metrics.llm.total_output_tokens += output_tokens
        if thinking_tokens is not None:
            _aggregated_metrics.llm.total_thinking_tokens += thinking_tokens
        _aggregated_metrics.llm.total_duration_ms += duration_ms
        
        # Update model-specific stats
        if model not in _aggregated_metrics.llm.by_model:
            _aggregated_metrics.llm.by_model[model] = ModelUsageStats()
        
        model_stats = _aggregated_metrics.llm.by_model[model]
        model_stats.call_count += 1
        model_stats.total_input_tokens += input_tokens
        model_stats.total_output_tokens += output_tokens
        if thinking_tokens is not None:
            model_stats.total_thinking_tokens += thinking_tokens
        model_stats.total_duration_ms += duration_ms
        
        # Update average TTFT
        if ttft_ms is not None:
            current_avg = _aggregated_metrics.llm.avg_ttft_ms
            total_calls = _aggregated_metrics.llm.total_calls
            if current_avg is None:
                _aggregated_metrics.llm.avg_ttft_ms = ttft_ms
            else:
                # Running average: (old_avg * (n-1) + new_value) / n
                _aggregated_metrics.llm.avg_ttft_ms = (current_avg * (total_calls - 1) + ttft_ms) / total_calls
    
    # Clean up timing data
    with _llm_call_starts_lock:
        if thread_id in _llm_call_starts and call_id in _llm_call_starts[thread_id]:
            del _llm_call_starts[thread_id][call_id]
            if not _llm_call_starts[thread_id]:
                del _llm_call_starts[thread_id]
    
    with _first_token_times_lock:
        if thread_id in _first_token_times and call_id in _first_token_times[thread_id]:
            del _first_token_times[thread_id][call_id]
            if not _first_token_times[thread_id]:
                del _first_token_times[thread_id]
    
    # Clean up run_id mapping
    with _run_id_to_call_id_lock:
        if thread_id in _run_id_to_call_id:
            # Find and remove the run_id that maps to this call_id
            to_remove = []
            for rid, cid in _run_id_to_call_id[thread_id].items():
                if cid == call_id:
                    to_remove.append(rid)
            for rid in to_remove:
                del _run_id_to_call_id[thread_id][rid]
            if not _run_id_to_call_id[thread_id]:
                del _run_id_to_call_id[thread_id]


def record_embedding_usage(
    thread_id: str | None = None,
    model: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
    duration_ms: float = 0.0,
) -> None:
    """Record embedding model usage metrics.
    
    Args:
        thread_id: Flow execution identifier (if None, uses current context)
        model: Embedding model name
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens (usually 0 for embeddings)
        duration_ms: Call duration in milliseconds
    """
    # Get thread_id from context if not provided
    if thread_id is None:
        thread_id = _current_thread_id.get()
        if thread_id is None:
            # Can't track without thread_id
            return
    usage = EmbeddingUsage(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        duration_ms=duration_ms,
        timestamp=datetime.utcnow(),
    )
    
    # Record per execution
    with _execution_metrics_lock:
        if thread_id not in _execution_metrics:
            initialize_execution(thread_id)
        _execution_metrics[thread_id].embedding_calls.append(usage)
    
    # Update aggregated metrics
    with _aggregated_metrics_lock:
        _aggregated_metrics.embeddings.total_calls += 1
        _aggregated_metrics.embeddings.total_input_tokens += input_tokens
        _aggregated_metrics.embeddings.total_duration_ms += duration_ms
        
        # Update model-specific stats
        if model not in _aggregated_metrics.embeddings.by_model:
            _aggregated_metrics.embeddings.by_model[model] = ModelUsageStats()
        
        model_stats = _aggregated_metrics.embeddings.by_model[model]
        model_stats.call_count += 1
        model_stats.total_input_tokens += input_tokens
        model_stats.total_output_tokens += output_tokens
        model_stats.total_duration_ms += duration_ms


def record_brightdata_usage(
    thread_id: str | None = None,
    duration_ms: float = 0.0,
    cost: float | None = None,
    bytes: int = 0,
) -> None:
    """Record Bright Data usage metrics.
    
    Args:
        thread_id: Flow execution identifier (if None, uses current context)
        duration_ms: Call duration in milliseconds
        cost: Cost of the call (if available)
        bytes: Number of bytes transferred (if available)
    """
    # Get thread_id from context if not provided
    if thread_id is None:
        thread_id = _current_thread_id.get()
        if thread_id is None:
            # Can't track without thread_id
            return
    # Record per execution
    with _execution_metrics_lock:
        if thread_id not in _execution_metrics:
            initialize_execution(thread_id)
        
        metrics = _execution_metrics[thread_id]
        metrics.brightdata_calls.call_count += 1
        metrics.brightdata_calls.total_duration_ms += duration_ms
        metrics.brightdata_calls.total_bytes += bytes
        if cost is not None:
            if metrics.brightdata_calls.total_cost is None:
                metrics.brightdata_calls.total_cost = 0.0
            metrics.brightdata_calls.total_cost += cost
    
    # Update aggregated metrics
    with _aggregated_metrics_lock:
        _aggregated_metrics.brightdata.total_calls += 1
        _aggregated_metrics.brightdata.total_duration_ms += duration_ms
        _aggregated_metrics.brightdata.total_bytes += bytes
        if cost is not None:
            if _aggregated_metrics.brightdata.total_cost is None:
                _aggregated_metrics.brightdata.total_cost = 0.0
            _aggregated_metrics.brightdata.total_cost += cost


def get_execution_metrics(thread_id: str) -> ExecutionMetrics | None:
    """Get metrics for a specific flow execution.
    
    Args:
        thread_id: Flow execution identifier
        
    Returns:
        ExecutionMetrics if found, None otherwise
    """
    with _execution_metrics_lock:
        return _execution_metrics.get(thread_id)


def get_aggregated_metrics() -> AggregatedMetrics:
    """Get aggregated metrics across all executions.
    
    Returns:
        AggregatedMetrics with totals
    """
    with _aggregated_metrics_lock:
        # Update total_executions count
        with _execution_metrics_lock:
            _aggregated_metrics.total_executions = len(_execution_metrics)
        return _aggregated_metrics.model_copy(deep=True)


def list_execution_thread_ids() -> list[str]:
    """List all tracked execution thread IDs.
    
    Returns:
        List of thread IDs
    """
    with _execution_metrics_lock:
        return list(_execution_metrics.keys())


def clear_execution_metrics(thread_id: str) -> None:
    """Clear metrics for a specific execution (cleanup).
    
    Args:
        thread_id: Flow execution identifier
    """
    with _execution_metrics_lock:
        if thread_id in _execution_metrics:
            del _execution_metrics[thread_id]
    
    # Clean up timing data
    with _llm_call_starts_lock:
        if thread_id in _llm_call_starts:
            del _llm_call_starts[thread_id]
    
    with _first_token_times_lock:
        if thread_id in _first_token_times:
            del _first_token_times[thread_id]
    
    with _run_id_to_call_id_lock:
        if thread_id in _run_id_to_call_id:
            del _run_id_to_call_id[thread_id]


# Create router for observability endpoints
router = APIRouter()


@router.get("/execution/{thread_id}")
async def get_execution_metrics_endpoint(
    thread_id: str,
    user_payload: dict = Depends(verify_google_token),
):
    """Get metrics for a specific flow execution.
    
    Args:
        thread_id: Flow execution identifier
        user_payload: Authenticated user payload
        
    Returns:
        ExecutionMetrics for the specified thread_id
        
    Raises:
        HTTPException: 404 if execution not found
    """
    metrics = get_execution_metrics(thread_id)
    
    if metrics is None:
        _get_logger().warning(
            "execution_metrics_not_found",
            thread_id=thread_id,
            user_id=user_payload.get("sub"),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execution metrics not found for thread_id: {thread_id}",
        )
    
    _get_logger().debug(
        "execution_metrics_retrieved",
        thread_id=thread_id,
        llm_calls=len(metrics.llm_calls),
        embedding_calls=len(metrics.embedding_calls),
        brightdata_calls=metrics.brightdata_calls.call_count,
    )
    
    return metrics.model_dump()


@router.get("/aggregated")
async def get_aggregated_metrics_endpoint(
    user_payload: dict = Depends(verify_google_token),
):
    """Get aggregated metrics across all executions.
    
    Args:
        user_payload: Authenticated user payload
        
    Returns:
        AggregatedMetrics with totals
    """
    metrics = get_aggregated_metrics()
    
    _get_logger().debug(
        "aggregated_metrics_retrieved",
        total_executions=metrics.total_executions,
        total_llm_calls=metrics.llm.total_calls,
        total_embedding_calls=metrics.embeddings.total_calls,
        total_brightdata_calls=metrics.brightdata.total_calls,
    )
    
    return metrics.model_dump()


@router.get("/executions")
async def list_executions_endpoint(
    user_payload: dict = Depends(verify_google_token),
):
    """List all tracked execution thread IDs.
    
    Args:
        user_payload: Authenticated user payload
        
    Returns:
        List of thread IDs
    """
    thread_ids = list_execution_thread_ids()
    
    _get_logger().debug(
        "execution_thread_ids_listed",
        count=len(thread_ids),
        user_id=user_payload.get("sub"),
    )
    
    return {
        "thread_ids": thread_ids,
        "count": len(thread_ids),
    }
