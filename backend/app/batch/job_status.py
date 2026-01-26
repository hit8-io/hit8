"""
Job execution status checking for Cloud Run batch jobs.
"""
from __future__ import annotations

from typing import Any

import structlog

from app.batch.client import get_jobs_client
from app.batch.types import JobStatus

logger = structlog.get_logger(__name__)


def _map_cloud_run_status_to_job_status(cloud_run_status: str) -> JobStatus:
    """Map Cloud Run execution status to JobStatus enum.
    
    Args:
        cloud_run_status: Cloud Run execution status string.
        
    Returns:
        JobStatus enum value.
    """
    status_mapping = {
        "EXECUTION_STATE_UNSPECIFIED": JobStatus.UNKNOWN,
        "EXECUTION_STATE_QUEUED": JobStatus.PENDING,
        "EXECUTION_STATE_RUNNING": JobStatus.RUNNING,
        "EXECUTION_STATE_SUCCEEDED": JobStatus.SUCCEEDED,
        "EXECUTION_STATE_FAILED": JobStatus.FAILED,
        "EXECUTION_STATE_CANCELLED": JobStatus.CANCELLED,
    }
    
    return status_mapping.get(cloud_run_status, JobStatus.UNKNOWN)


async def get_execution_status(execution_name: str) -> dict[str, Any] | None:
    """Get Cloud Run execution status.
    
    Args:
        execution_name: Full execution name (projects/.../executions/...).
        
    Returns:
        Dictionary with execution status information, or None if not found/error.
        Contains:
        - status: JobStatus enum value
        - completion_time: ISO timestamp if completed
        - error_message: Error message if failed
    """
    run_jobs_client = get_jobs_client()
    if not run_jobs_client:
        logger.warning(
            "cloud_run_jobs_client_not_available_for_status",
            execution_name=execution_name,
        )
        return None
    
    try:
        from google.cloud.run_v2 import ExecutionsClient
        from google.oauth2 import service_account
        import json
        from app.config import settings
        
        # Create Executions client (similar to Jobs client)
        service_account_info = json.loads(settings.VERTEX_SERVICE_ACCOUNT)
        credentials = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        executions_client = ExecutionsClient(credentials=credentials)
        
        # Get execution
        execution = executions_client.get_execution(name=execution_name)
        
        # Extract status
        status_str = execution.reconciling_condition.state.name if execution.reconciling_condition else "UNKNOWN"
        job_status = _map_cloud_run_status_to_job_status(status_str)
        
        result = {
            "status": job_status,
            "completion_time": None,
            "error_message": None,
        }
        
        # Extract completion time if available
        if hasattr(execution, 'completion_time') and execution.completion_time:
            result["completion_time"] = execution.completion_time.isoformat()
        
        # Extract error message if failed
        if job_status == JobStatus.FAILED:
            if hasattr(execution, 'conditions') and execution.conditions:
                for condition in execution.conditions:
                    if condition.type == "Failed" and condition.message:
                        result["error_message"] = condition.message
                        break
        
        return result
        
    except Exception as e:
        logger.warning(
            "failed_to_get_execution_status",
            execution_name=execution_name,
            error=str(e),
            error_type=type(e).__name__,
        )
        return None


async def get_job_status_for_thread(
    thread_id: str,
    org: str,
    project: str,
    execution_name: str | None = None,
) -> dict[str, Any]:
    """Get combined job status for a thread (graph state + Cloud Run status).
    
    Args:
        thread_id: Thread ID.
        org: Organization name.
        project: Project name.
        execution_name: Optional execution name. If provided, checks Cloud Run status.
        
    Returns:
        Dictionary with combined status information.
    """
    # First, try to get graph state
    from app.api.graph_manager import get_graph
    
    config = {"configurable": {"thread_id": thread_id}}
    report_graph = get_graph(org, project, "report")
    
    try:
        import asyncio
        snapshot = await asyncio.to_thread(report_graph.get_state, config)
        
        if snapshot.values:
            # Graph state exists - use it
            current_values = snapshot.values
            chapters = current_values.get("chapters", [])
            logs = current_values.get("logs", [])
            is_complete = "final_report" in current_values
            
            next_nodes = list(snapshot.next) if snapshot.next else []
            visited_nodes = []
            if snapshot.tasks:
                visited_nodes = [t.name for t in snapshot.tasks if hasattr(t, 'name')]
            
            return {
                "status": "completed" if is_complete else "running",
                "progress": {
                    "chapters_completed": len(chapters),
                    "recent_logs": logs[-20:] if logs else [],
                },
                "graph_state": {
                    "visited_nodes": visited_nodes,
                    "next": next_nodes,
                },
                # Include full state for frontend to render clusters, chapters, etc.
                "state": {
                    "raw_procedures": current_values.get("raw_procedures", []),
                    "pending_clusters": current_values.get("pending_clusters", []),
                    "clusters_all": current_values.get("clusters_all"),
                    "cluster_status": current_values.get("cluster_status", {}),
                    "chapters": chapters,
                    "chapters_by_file_id": current_values.get("chapters_by_file_id", {}),
                    "final_report": current_values.get("final_report") if is_complete else None,
                },
                "result": current_values.get("final_report") if is_complete else None,
            }
    except Exception as e:
        # Graph state not found or error reading it - check Cloud Run status if execution_name provided
        logger.debug(
            "get_job_status_graph_state_error",
            thread_id=thread_id,
            error=str(e),
            error_type=type(e).__name__,
        )
    
    # If graph state not found and we have execution_name, check Cloud Run status
    if execution_name:
        cloud_run_status = await get_execution_status(execution_name)
        if cloud_run_status:
            status = cloud_run_status["status"]
            return {
                "status": status.value if isinstance(status, JobStatus) else str(status),
                "progress": {},
                "graph_state": {
                    "visited_nodes": [],
                    "next": [],
                },
                "state": None,
                "error_message": cloud_run_status.get("error_message"),
            }
    
    # No state found
    return {
        "status": "not_found",
        "progress": {},
        "graph_state": {
            "visited_nodes": [],
            "next": [],
        },
        "state": None,
    }
