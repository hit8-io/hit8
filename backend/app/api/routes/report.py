"""
API Routes for the Report Engine.
"""
import asyncio
import threading
import uuid
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, BackgroundTasks, HTTPException, Body, Depends, Header
import structlog

from app.auth import verify_google_token
from app.user_config import validate_user_access
from app.api.checkpointer import checkpointer
from app.api.graph_manager import get_graph

logger = structlog.get_logger(__name__)

# Global registry for active report tasks to support "Stop" functionality
_active_tasks: Dict[str, asyncio.Task] = {}

# Cloud Run Jobs client (lazy initialization)
_run_jobs_client = None
_run_jobs_client_lock = threading.Lock()

def _get_run_jobs_client():
    """Get or create Cloud Run Jobs client instance."""
    global _run_jobs_client
    if _run_jobs_client is None:
        with _run_jobs_client_lock:
            if _run_jobs_client is None:
                try:
                    from google.cloud import run_v2
                    from google.oauth2 import service_account
                    import json
                    from app.config import settings
                    
                    service_account_info = json.loads(settings.VERTEX_SERVICE_ACCOUNT)
                    credentials = service_account.Credentials.from_service_account_info(
                        service_account_info,
                        scopes=["https://www.googleapis.com/auth/cloud-platform"]
                    )
                    _run_jobs_client = run_v2.JobsClient(credentials=credentials)
                    logger.debug("cloud_run_jobs_client_initialized")
                except ImportError:
                    logger.warning("cloud_run_jobs_client_not_available", reason="google-cloud-run not installed")
                    _run_jobs_client = False
                except Exception as e:
                    logger.error(
                        "cloud_run_jobs_client_init_failed",
                        error=str(e),
                        error_type=type(e).__name__,
                    )
                    _run_jobs_client = False
    return _run_jobs_client if _run_jobs_client is not False else None

router = APIRouter(prefix="/report", tags=["Report"])

# --- Models ---
# Using untyped dicts for simplicity in this POC, but typically use Pydantic
# payload: {"procedures": [...], "execution_mode": "local" | "cloud_run_service" | "cloud_run_job"}

@router.post("/start")
async def start_report(
    background_tasks: BackgroundTasks, 
    payload: Dict[str, Any] = Body(...),
    user_payload: dict = Depends(verify_google_token),
    x_org: str | None = Header(None, alias="X-Org"),
    x_project: str | None = Header(None, alias="X-Project"),
):
    """
    Starts a new report generation job.
    """
    email = user_payload["email"]
    org = (x_org or "").strip()
    project = (x_project or "").strip()
    
    if not org or not project:
        raise HTTPException(
            status_code=400,
            detail="Organization and project must be selected before starting a report."
        )
    
    # Validate user has access to the requested org/project
    if not validate_user_access(email, org, project):
        logger.warning(
            "user_access_denied",
            email=email,
            org=org,
            project=project,
            action="start_report",
        )
        raise HTTPException(
            status_code=403,
            detail=f"User does not have access to org '{org}' / project '{project}'",
        )
    thread_id = str(uuid.uuid4())
    procedures = payload.get("procedures", [])
    mode = payload.get("execution_mode", "local")
    
    # Validate execution mode
    valid_modes = ["local", "cloud_run_service", "cloud_run_job"]
    if mode not in valid_modes:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid execution_mode '{mode}'. Must be one of: {', '.join(valid_modes)}"
        )
    
    initial_state = {"raw_procedures": procedures}
    config = {
        "configurable": {
            "thread_id": thread_id, 
            "checkpointer": checkpointer
        }
    }
    
    if mode == "cloud_run_job":
        # --- Trigger Cloud Run Job ---
        run_jobs_client = _get_run_jobs_client()
        if not run_jobs_client:
            raise HTTPException(
                status_code=501,
                detail="Cloud Run Jobs client is not available. Please install 'google-cloud-run' and ensure GCP credentials are configured."
            )
        
        try:
            from google.cloud.run_v2.types import RunJobRequest, EnvVar
            from app.config import settings
            import json
            
            # Job name format: projects/{project}/locations/{location}/jobs/{job}
            job_name = f"projects/{settings.GCP_PROJECT}/locations/{settings.VERTEX_AI_LOCATION}/jobs/hit8-report-job"
            
            # Create execution overrides with environment variables
            # Pass job parameters as JSON in environment variable for simplicity
            job_params = {
                "thread_id": thread_id,
                "org": org,
                "project": project,
                "procedures": procedures,
            }
            
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
            )
            
            return {
                "job_id": thread_id,
                "status": "cloud_run_job_submitted",
                "execution_name": execution_name,
                "mode": mode,
            }
        except Exception as e:
            logger.exception(
                "cloud_run_job_trigger_failed",
                thread_id=thread_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to trigger Cloud Run Job: {str(e)}"
            )
    
    elif mode == "cloud_run_service":
        # --- Cloud Run Service Mode (async execution in same service) ---
        # Get the report graph instance
        report_graph = get_graph(org, project, "report")
        
        # Wrap in a coroutine so we can track and cancel it
        async def run_report():
            try:
                await report_graph.ainvoke(initial_state, config)
            except asyncio.CancelledError:
                logger.info("report_execution_cancelled", thread_id=thread_id)
            except Exception as e:
                logger.exception(
                    "report_execution_failed",
                    thread_id=thread_id,
                    error=str(e),
                    error_type=type(e).__name__,
                )
            finally:
                _active_tasks.pop(thread_id, None)
        
        task = asyncio.create_task(run_report())
        _active_tasks[thread_id] = task
        
        logger.info(
            "cloud_run_service_report_started",
            thread_id=thread_id,
            org=org,
            project=project,
        )
        
        return {"job_id": thread_id, "status": "started", "mode": mode}
    
    else:  # mode == "local"
        # --- Local Background Task ---
        # Get the report graph instance
        report_graph = get_graph(org, project, "report")
        
        # Wrap in a coroutine so we can track and cancel it
        async def run_report():
            try:
                await report_graph.ainvoke(initial_state, config)
            except asyncio.CancelledError:
                logger.info("report_execution_cancelled", thread_id=thread_id)
            except Exception as e:
                logger.exception(
                    "report_execution_failed",
                    thread_id=thread_id,
                    error=str(e),
                    error_type=type(e).__name__,
                )
            finally:
                _active_tasks.pop(thread_id, None)

        task = asyncio.create_task(run_report())
        _active_tasks[thread_id] = task
        
        logger.info(
            "local_report_started",
            thread_id=thread_id,
            org=org,
            project=project,
        )
    
    return {"job_id": thread_id, "status": "started", "mode": mode}

@router.post("/{thread_id}/stop")
async def stop_report(
    thread_id: str,
    user_payload: dict = Depends(verify_google_token),
):
    """Stops an ongoing report generation."""
    task = _active_tasks.get(thread_id)
    if not task:
        return {"status": "not_running", "message": "No active task found for this ID."}
    
    task.cancel()
    return {"status": "stopping", "message": "Termination signal sent to agent."}

@router.get("/{thread_id}/status")
async def get_status(
    thread_id: str,
    user_payload: dict = Depends(verify_google_token),
    x_org: str | None = Header(None, alias="X-Org"),
    x_project: str | None = Header(None, alias="X-Project"),
):
    """Gets granular status (e.g. 5/10 chapters done)."""
    email = user_payload["email"]
    org = (x_org or "").strip()
    project = (x_project or "").strip()
    
    if not org or not project:
        raise HTTPException(
            status_code=400,
            detail="Organization and project must be selected."
        )
    
    # Validate user has access to the requested org/project
    if not validate_user_access(email, org, project):
        logger.warning(
            "user_access_denied",
            email=email,
            org=org,
            project=project,
            action="get_status",
        )
        raise HTTPException(
            status_code=403,
            detail=f"User does not have access to org '{org}' / project '{project}'",
        )
    
    config = {"configurable": {"thread_id": thread_id, "checkpointer": checkpointer}}
    
    # Get the report graph instance
    report_graph = get_graph(org, project, "report")
    
    # Check local state
    try:
        snapshot = await report_graph.get_state(config)
    except Exception:
        return {"status": "not_found"}
    
    if not snapshot.values:
        return {"status": "not_found_or_empty"}
    
    current_values = snapshot.values
    chapters = current_values.get("chapters", [])
    logs = current_values.get("logs", [])
    
    is_complete = "final_report" in current_values
    
    # We can determine "visited" nodes by looking at history or 
    # just returning the current node and what's next.
    # For a simpler integration with GraphView:
    next_nodes = list(snapshot.next) if snapshot.next else []
    
    # Deriving visited nodes from history
    visited_nodes = []
    try:
        async for state_item in report_graph.get_state_history(config):
            # The state_item.metadata['source'] often indicates the node
            # But simpler is to look at the tasks in history
            if state_item.tasks:
                for t in state_item.tasks:
                    if t.name not in visited_nodes:
                        visited_nodes.append(t.name)
    except Exception:
        pass

    return {
        "status": "completed" if is_complete else "running",
        "progress": {
            "chapters_completed": len(chapters),
            "recent_logs": logs
        },
        "graph_state": {
            "visited_nodes": visited_nodes,
            "next": next_nodes
        },
        "result": current_values.get("final_report") if is_complete else None
    }

@router.post("/{thread_id}/resume")
async def resume_report(
    thread_id: str,
    background_tasks: BackgroundTasks,
    user_payload: dict = Depends(verify_google_token),
    x_org: str | None = Header(None, alias="X-Org"),
    x_project: str | None = Header(None, alias="X-Project"),
):
    """Resumes a stopped/paused workflow from the last checkpoint."""
    email = user_payload["email"]
    org = (x_org or "").strip()
    project = (x_project or "").strip()
    
    if not org or not project:
        raise HTTPException(
            status_code=400,
            detail="Organization and project must be selected."
        )
    
    # Validate user has access to the requested org/project
    if not validate_user_access(email, org, project):
        logger.warning(
            "user_access_denied",
            email=email,
            org=org,
            project=project,
            action="resume_report",
        )
        raise HTTPException(
            status_code=403,
            detail=f"User does not have access to org '{org}' / project '{project}'",
        )
    
    config = {"configurable": {"thread_id": thread_id, "checkpointer": checkpointer}}
    
    # Get the report graph instance
    report_graph = get_graph(org, project, "report")
    
    # Calling invoke with None input triggers continuation
    background_tasks.add_task(report_graph.ainvoke, None, config)
    
    return {"status": "resuming"}


@router.post("/job/execute")
async def execute_report_job(
    payload: Dict[str, Any] = Body(...),
):
    """
    Internal endpoint for Cloud Run Job execution.
    Called by Cloud Run Job container to execute a report.
    Requires API_TOKEN authentication via header.
    """
    import os
    from app.config import settings
    
    # Authenticate using API_TOKEN (internal service-to-service auth)
    api_token = os.getenv("API_TOKEN")
    if not api_token or api_token != settings.API_TOKEN:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API token"
        )
    
    # Get job parameters from payload or environment variables
    # Environment variables take precedence (set by Cloud Run Job)
    job_params_env = os.getenv("REPORT_JOB_PARAMS")
    if job_params_env:
        import json
        try:
            job_params = json.loads(job_params_env)
            thread_id = job_params.get("thread_id")
            org = job_params.get("org")
            project = job_params.get("project")
            procedures = job_params.get("procedures", [])
        except (json.JSONDecodeError, KeyError) as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid REPORT_JOB_PARAMS: {str(e)}"
            )
    else:
        # Fallback to payload
        thread_id = payload.get("thread_id")
        org = payload.get("org")
        project = payload.get("project")
        procedures = payload.get("procedures", [])
    
    if not all([thread_id, org, project]):
        raise HTTPException(
            status_code=400,
            detail="Missing required parameters: thread_id, org, project"
        )
    
    initial_state = {"raw_procedures": procedures}
    config = {
        "configurable": {
            "thread_id": thread_id,
            "checkpointer": checkpointer
        }
    }
    
    # Get the report graph instance
    report_graph = get_graph(org, project, "report")
    
    logger.info(
        "report_job_execution_started",
        thread_id=thread_id,
        org=org,
        project=project,
    )
    
    try:
        # Execute the report graph
        await report_graph.ainvoke(initial_state, config)
        
        logger.info(
            "report_job_execution_completed",
            thread_id=thread_id,
            org=org,
            project=project,
        )
        
        return {"status": "completed", "thread_id": thread_id}
    except Exception as e:
        logger.exception(
            "report_job_execution_failed",
            thread_id=thread_id,
            org=org,
            project=project,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Report execution failed: {str(e)}"
        )
