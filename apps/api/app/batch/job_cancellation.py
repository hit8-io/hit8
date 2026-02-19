"""
Job cancellation logic for Cloud Run batch jobs.
"""
from __future__ import annotations

import json

import structlog

from app.batch.client import get_jobs_client
from app.batch.types import JobStatus

logger = structlog.get_logger(__name__)


async def cancel_execution(execution_name: str) -> bool:
    """Cancel a Cloud Run job execution.
    
    Args:
        execution_name: Full execution name (projects/.../executions/...).
        
    Returns:
        True if cancellation was successful, False otherwise.
    """
    run_jobs_client = get_jobs_client()
    if not run_jobs_client:
        logger.warning(
            "cloud_run_jobs_client_not_available_for_cancellation",
            execution_name=execution_name,
        )
        return False
    
    try:
        from google.cloud.run_v2 import ExecutionsClient
        from google.oauth2 import service_account
        from app.config import settings
        
        # Create Executions client
        service_account_info = json.loads(settings.VERTEX_SERVICE_ACCOUNT)
        credentials = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        executions_client = ExecutionsClient(credentials=credentials)
        
        # Cancel execution
        from google.cloud.run_v2.types import CancelExecutionRequest
        request = CancelExecutionRequest(name=execution_name)
        operation = executions_client.cancel_execution(request=request)
        
        logger.info(
            "cloud_run_execution_cancelled",
            execution_name=execution_name,
            operation_name=operation.name if hasattr(operation, 'name') else None,
        )
        
        return True
        
    except Exception as e:
        logger.error(
            "failed_to_cancel_execution",
            execution_name=execution_name,
            error=str(e),
            error_type=type(e).__name__,
        )
        return False


def _get_cancelled_threads() -> dict[str, bool]:
    """Get the cancelled threads registry.
    
    Returns:
        Dictionary mapping thread_id to cancellation status.
    """
    # Import here to avoid circular dependency
    from app.api.routes.report import _cancelled_threads
    return _cancelled_threads


async def cancel_report_job(thread_id: str, execution_name: str | None = None) -> bool:
    """Cancel a report job execution.
    
    This function cancels the Cloud Run execution if execution_name is provided.
    It also sets a cancellation flag that the running job can check for graceful shutdown.
    
    Args:
        thread_id: Thread ID of the report execution.
        execution_name: Optional execution name. If provided, cancels the Cloud Run execution.
        
    Returns:
        True if cancellation was successful or attempted, False otherwise.
    """
    # Set cancellation flag for graceful shutdown (checked in event loop)
    cancelled_threads = _get_cancelled_threads()
    cancelled_threads[thread_id] = True
    
    logger.info(
        "report_job_cancellation_requested",
        thread_id=thread_id,
        execution_name=execution_name,
    )
    
    # Cancel Cloud Run execution if execution_name provided
    if execution_name:
        success = await cancel_execution(execution_name)
        if success:
            logger.info(
                "report_job_cloud_run_execution_cancelled",
                thread_id=thread_id,
                execution_name=execution_name,
            )
        return success
    
    # Cancellation flag set, but no execution to cancel
    logger.info(
        "report_job_cancellation_flag_set",
        thread_id=thread_id,
        note="No execution_name provided, only cancellation flag set",
    )
    return True
