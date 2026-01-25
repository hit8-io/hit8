"""
Job triggering logic for Cloud Run batch jobs.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

import structlog

from app.batch.client import get_jobs_client
from app.batch.types import JOB_NAME_PREFIX
from app.config import settings
from app.flows.common import _get_first_available_llm_config

if TYPE_CHECKING:
    from google.cloud.run_v2.types import RunJobRequest

logger = structlog.get_logger(__name__)


def _get_environment_suffix(environment: str | None = None) -> str:
    """Get environment suffix for job name.
    
    Args:
        environment: Environment name (prd, stg, dev). If None, uses settings.environment.
        
    Returns:
        Environment suffix: "-prd", "-stg", or "" for dev.
    """
    if environment is None:
        environment = settings.environment
    
    if environment == "prd":
        return "-prd"
    elif environment == "stg":
        return "-stg"
    else:
        return ""


def _get_job_location() -> str:
    """Get Cloud Run job location.
    
    Returns:
        Location string (e.g., "europe-west1").
    """
    llm_config = _get_first_available_llm_config()
    location = llm_config.get("LOCATION") if llm_config else None
    if location:
        return location
    
    # Fallback to deprecated setting
    if settings.VERTEX_AI_LOCATION:
        return settings.VERTEX_AI_LOCATION
    
    # Default location
    return "europe-west1"


def _build_job_name(environment: str | None = None) -> str:
    """Build Cloud Run job name with environment suffix.
    
    Args:
        environment: Environment name. If None, uses settings.environment.
        
    Returns:
        Full job name: projects/{project}/locations/{location}/jobs/hit8-report-job{suffix}
    """
    suffix = _get_environment_suffix(environment)
    job_name_base = f"{JOB_NAME_PREFIX}{suffix}"
    location = _get_job_location()
    
    return f"projects/{settings.GCP_PROJECT}/locations/{location}/jobs/{job_name_base}"


async def trigger_report_job(
    thread_id: str,
    org: str,
    project: str,
    model: str | None = None,
    environment: str | None = None,
) -> str | None:
    """Trigger a Cloud Run batch job for report generation.
    
    Args:
        thread_id: Thread ID for the report execution.
        org: Organization name.
        project: Project name.
        model: Optional model name to use.
        environment: Optional environment name. If None, uses settings.environment.
        
    Returns:
        Execution name if job was triggered successfully, None otherwise.
        
    Raises:
        RuntimeError: If Cloud Run Jobs client is not available.
        Exception: If job triggering fails.
    """
    run_jobs_client = get_jobs_client()
    if not run_jobs_client:
        raise RuntimeError(
            "Cloud Run Jobs client is not available. "
            "Please install 'google-cloud-run' and ensure GCP credentials are configured."
        )
    
    try:
        from google.cloud.run_v2.types import RunJobRequest, EnvVar
        
        job_name = _build_job_name(environment)
        
        # Create execution overrides with environment variables
        # Pass job parameters as JSON in environment variable for simplicity
        job_params = {
            "thread_id": thread_id,
            "org": org,
            "project": project,
        }
        if model:
            job_params["model"] = model
        
        overrides = RunJobRequest.Overrides(
            container_overrides=[
                RunJobRequest.Overrides.ContainerOverride(
                    env=[
                        EnvVar(name="REPORT_JOB_PARAMS", value=json.dumps(job_params)),
                    ]
                )
            ]
        )
        
        # Execute the job
        request = RunJobRequest(
            name=job_name,
            overrides=overrides,
        )
        
        operation = run_jobs_client.run_job(request=request)
        
        # The operation is a long-running operation, get the execution name from metadata
        execution_name = None
        if hasattr(operation, 'metadata') and hasattr(operation.metadata, 'name'):
            execution_name = operation.metadata.name
        
        logger.info(
            "cloud_run_job_triggered",
            thread_id=thread_id,
            job_name=job_name,
            execution_name=execution_name,
            org=org,
            project=project,
            environment=environment or settings.environment,
        )
        
        return execution_name
        
    except Exception as e:
        logger.exception(
            "cloud_run_job_trigger_failed",
            thread_id=thread_id,
            error=str(e),
            error_type=type(e).__name__,
            org=org,
            project=project,
        )
        raise
