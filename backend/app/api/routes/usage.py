"""
Usage metrics API endpoints.
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.observability import (
    get_aggregated_metrics,
    get_execution_metrics,
    list_execution_thread_ids,
)
from app.auth import verify_google_token

logger = structlog.get_logger(__name__)
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
        logger.warning(
            "execution_metrics_not_found",
            thread_id=thread_id,
            user_id=user_payload.get("sub"),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execution metrics not found for thread_id: {thread_id}",
        )
    
    logger.debug(
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
    
    logger.debug(
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
    
    logger.debug(
        "execution_thread_ids_listed",
        count=len(thread_ids),
        user_id=user_payload.get("sub"),
    )
    
    return {
        "thread_ids": thread_ids,
        "count": len(thread_ids),
    }
