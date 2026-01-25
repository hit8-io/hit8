"""
API Routes for the Report Engine.
"""
import asyncio
import threading
import uuid
import json
import os
import tempfile
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, BackgroundTasks, HTTPException, Body, Depends, Header
from fastapi.responses import StreamingResponse
import structlog
import pypandoc

from app.auth import verify_google_token
from app.user_config import validate_user_access, validate_user_flow_access
from app.api.graph_manager import get_graph
from app.api.streaming.async_events import process_async_stream_events
from app.api.constants import EVENT_GRAPH_END, EVENT_ERROR
from app.flows.opgroeien.poc.db import _get_all_procedures_raw_sql
from app.flows.common import _get_first_available_llm_config
from app.api.user_threads import upsert_thread
from app.constants import CONSTANTS

logger = structlog.get_logger(__name__)


def _resolve_report_model(user_model: str | None) -> str | None:
    """Return user-chosen model or first available so analyst, editor and consult share one model."""
    if user_model:
        return user_model
    cfg = _get_first_available_llm_config()
    return (cfg or {}).get("MODEL_NAME")

# Global registry for active report tasks to support "Stop" functionality
_active_tasks: Dict[str, asyncio.Task] = {}

# Simple cancellation registry - checked between nodes (no polling)
# When True, current nodes finish but no new nodes start
_cancelled_threads: Dict[str, bool] = {}

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

async def stream_report_events(
    initial_state: Dict[str, Any],
    config: Dict[str, Any],
    thread_id: str,
    org: str,
    project: str,
):
    """Stream report execution events using LangGraph astream_events() directly.
    
    Similar to stream_chat_events but for report generation.
    
    Yields:
        Server-Sent Event strings
    """
    try:
        # Set thread_id in observability context
        try:
            from app.api.observability import _current_thread_id, initialize_execution
            _current_thread_id.set(thread_id)
            initialize_execution(thread_id)
        except Exception:
            # Don't fail if observability is not available
            pass
        
        logger.info(
            "report_stream_started",
            thread_id=thread_id,
            org=org,
            project=project,
        )
        
        # Get the report graph instance
        report_graph = get_graph(org, project, "report")
        
        # Process events directly from astream_events - runs in main event loop
        accumulated_content_ref: dict[str, str] = {"content": ""}
        
        async for event_str in process_async_stream_events(
            report_graph, initial_state, config, thread_id, org, project, accumulated_content_ref, flow="report"
        ):
            yield event_str
        
        # Get final state to extract final_report
        try:
            snapshot = await asyncio.to_thread(report_graph.get_state, config)
            final_report = snapshot.values.get("final_report", "") if snapshot.values else ""
        except Exception:
            final_report = ""
        
        # Always send graph_end event
        logger.debug(
            "report_graph_end_event",
            thread_id=thread_id,
            has_final_report=bool(final_report),
        )
        
        state_data = {
            "type": EVENT_GRAPH_END,
            "thread_id": thread_id,
            "response": final_report or "",
        }
        yield f"data: {json.dumps(state_data)}\n\n"
        
    except Exception as e:
        error_type = type(e).__name__
        error_str = str(e) if str(e) else ""
        error_message = error_str if error_str else f"{error_type}: An error occurred during streaming"
        
        # Check if this is a connection error (Ollama, database, etc.)
        is_connection_error = (
            "Connection refused" in error_str or
            "Errno 111" in error_str or
            "All connection attempts failed" in error_str or
            "ConnectError" in error_type or
            "ConnectionError" in error_type
        )
        
        logger.exception(
            "report_streaming_error",
            error=error_message,
            error_type=error_type,
            error_repr=repr(e),
            thread_id=thread_id,
            is_connection_error=is_connection_error,
            org=org,
            project=project,
            exc_info=True,
        )
        
        error_data = {
            "type": EVENT_ERROR,
            "error": error_message,
            "error_type": error_type,
            "thread_id": thread_id,
        }
        yield f"data: {json.dumps(error_data)}\n\n"
    finally:
        # Finalize execution metrics tracking
        try:
            from app.api.observability import finalize_execution
            finalize_execution(thread_id)
        except Exception:
            pass

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
    logger.info(
        "report_start_endpoint_called",
        has_payload=bool(payload),
        execution_mode=payload.get("execution_mode") if payload else None,
    )
    
    user_id = user_payload["sub"]
    email = user_payload["email"]
    org = (x_org or "").strip()
    project = (x_project or "").strip()
    
    logger.info(
        "report_start_processing",
        user_id=user_id,
        email=email,
        org=org,
        project=project,
    )
    
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
    
    # Validate user has access to report flow for this org/project
    if not validate_user_flow_access(email, org, project, "report"):
        logger.warning(
            "user_flow_access_denied",
            email=email,
            org=org,
            project=project,
            flow="report",
            action="start_report",
        )
        raise HTTPException(
            status_code=403,
            detail=f"User does not have access to 'report' flow for org '{org}' / project '{project}'",
        )
    # Get thread_id from payload if provided, otherwise generate new one
    thread_id = payload.get("thread_id")
    if not thread_id or not isinstance(thread_id, str):
        thread_id = str(uuid.uuid4())
    else:
        # Validate thread_id is a valid UUID format
        try:
            uuid.UUID(thread_id)
        except (ValueError, TypeError):
            # Invalid UUID format, generate new one
            thread_id = str(uuid.uuid4())
    
    # Clear any previous cancellation flag for this thread
    _cancelled_threads.pop(thread_id, None)
    
    # Derive flow identifier: "{org}.{project}.report"
    flow_identifier = f"{org}.{project}.report"
    
    # Track thread in database (non-blocking - errors are logged but don't fail the request)
    # Uses upsert to handle both new threads (create) and existing threads (update last_accessed_at)
    try:
        await upsert_thread(thread_id, user_id, title=None, flow=flow_identifier)
    except Exception as e:
        # Log error but don't fail the request if thread tracking fails
        logger.warning(
            "report_thread_tracking_failed",
            thread_id=thread_id,
            user_id=user_id,
            flow=flow_identifier,
            error=str(e),
            error_type=type(e).__name__,
        )
    mode = payload.get("execution_mode", "local")
    
    # Validate execution mode
    valid_modes = ["local", "cloud_run_service", "cloud_run_job"]
    if mode not in valid_modes:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid execution_mode '{mode}'. Must be one of: {', '.join(valid_modes)}"
        )
    
    # Fetch all procedures from database
    try:
        procedures = _get_all_procedures_raw_sql()
        logger.info(
            "procedures_fetched_from_database",
            thread_id=thread_id,
            procedure_count=len(procedures),
        )
    except Exception as e:
        logger.exception(
            "failed_to_fetch_procedures",
            thread_id=thread_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch procedures from database: {str(e)}"
        )
    
    # Initialize state for new report - clear final_report from any previous run
    initial_state = {
        "raw_procedures": procedures,
        "final_report": "",  # Clear any previous final_report
    }
    model = _resolve_report_model(payload.get("model"))
    config = {
        "configurable": {
            "thread_id": thread_id
        },
        "recursion_limit": CONSTANTS.get("GRAPH_RECURSION_LIMIT", 50),  # Prevent infinite loops
    }
    if model:
        config["configurable"]["model_name"] = model

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
            llm_config = _get_first_available_llm_config()
            location = llm_config.get("LOCATION") or settings.VERTEX_AI_LOCATION or "europe-west1"
            job_name = f"projects/{settings.GCP_PROJECT}/locations/{location}/jobs/hit8-report-job"
            
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
        # --- Cloud Run Service Mode (same as local - streaming) ---
        # Stream events directly like local mode
        # This keeps the connection alive and provides real-time feedback
        logger.info(
            "cloud_run_service_mode_entered",
            thread_id=thread_id,
            org=org,
            project=project,
        )
        return StreamingResponse(
            stream_report_events(
                initial_state=initial_state,
                config=config,
                thread_id=thread_id,
                org=org,
                project=project,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            },
        )
    
    else:  # mode == "local"
        # --- Local Streaming Mode ---
        # Stream events directly like chat endpoint
        return StreamingResponse(
            stream_report_events(
                initial_state=initial_state,
                config=config,
                thread_id=thread_id,
                org=org,
                project=project,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            },
        )

@router.get("/{thread_id}/snapshots")
async def list_snapshots(
    thread_id: str,
    user_payload: dict = Depends(verify_google_token),
    x_org: str | None = Header(None, alias="X-Org"),
    x_project: str | None = Header(None, alias="X-Project"),
):
    """List available snapshots for a thread_id (for restore capability)."""
    user_id = user_payload["sub"]
    email = user_payload["email"]
    org = (x_org or "").strip()
    project = (x_project or "").strip()
    
    if not org or not project:
        raise HTTPException(
            status_code=400,
            detail="Organization and project must be selected."
        )
    
    if not validate_user_access(email, org, project):
        raise HTTPException(
            status_code=403,
            detail=f"User does not have access to org '{org}' / project '{project}'",
        )
    
    # Derive flow identifier: "{org}.{project}.report"
    flow_identifier = f"{org}.{project}.report"
    
    # Update last_accessed_at for this thread (non-blocking)
    try:
        await upsert_thread(thread_id, user_id, title=None, flow=flow_identifier)
    except Exception as e:
        logger.warning(
            "report_thread_tracking_failed",
            thread_id=thread_id,
            user_id=user_id,
            flow=flow_identifier,
            error=str(e),
            error_type=type(e).__name__,
        )
    
    # Get the report graph instance
    report_graph = get_graph(org, project, "report")
    config = {"configurable": {"thread_id": thread_id}}
    
    try:
        # Get current state to extract snapshot info
        state = await report_graph.aget_state(config) if hasattr(report_graph, "aget_state") else await asyncio.to_thread(report_graph.get_state, config)
        
        # Extract snapshot information from state
        snapshots = []
        if state and hasattr(state, "tasks") and state.tasks:
            # Each task represents a checkpoint
            for i, task in enumerate(state.tasks):
                checkpoint_id = None
                if hasattr(task, "checkpoint_id"):
                    checkpoint_id = task.checkpoint_id
                elif isinstance(task, dict) and "checkpoint_id" in task:
                    checkpoint_id = task["checkpoint_id"]
                
                if checkpoint_id:
                    # Create human-readable label
                    from datetime import datetime
                    timestamp = datetime.utcnow().isoformat() + "Z"
                    label = f"Checkpoint {i+1} - {timestamp}"
                    
                    # Extract state summary
                    state_summary = {
                        "next_nodes": list(state.next) if hasattr(state, "next") and state.next else [],
                        "visited_nodes": [t.name if hasattr(t, "name") else str(t) for t in state.tasks[:i+1]] if hasattr(state, "tasks") else [],
                    }
                    
                    # For report flow, include cluster info
                    if hasattr(state, "values") and state.values:
                        values = state.values if isinstance(state.values, dict) else {}
                        if "pending_clusters" in values:
                            pending = values.get("pending_clusters", [])
                            chapters = values.get("chapters", [])
                            state_summary["pending_clusters_count"] = len(pending) if isinstance(pending, list) else 0
                            state_summary["chapters_count"] = len(chapters) if isinstance(chapters, list) else 0
                    
                    snapshots.append({
                        "snapshot_id": f"{checkpoint_id}:{i+1}",
                        "checkpoint_id": checkpoint_id,
                        "snapshot_seq": i+1,
                        "timestamp": timestamp,
                        "human_readable_label": label,
                        "state_summary": state_summary,
                    })
        
        return {"snapshots": snapshots}
    except Exception as e:
        logger.exception(
            "failed_to_list_snapshots",
            thread_id=thread_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list snapshots: {str(e)}"
        )


@router.post("/{thread_id}/restore")
async def restore_report(
    thread_id: str,
    payload: Dict[str, Any] = Body(...),
    user_payload: dict = Depends(verify_google_token),
    x_org: str | None = Header(None, alias="X-Org"),
    x_project: str | None = Header(None, alias="X-Project"),
):
    """Restore/resume execution from a specific snapshot."""
    user_id = user_payload["sub"]
    email = user_payload["email"]
    org = (x_org or "").strip()
    project = (x_project or "").strip()
    snapshot_id = payload.get("snapshot_id")
    
    if not org or not project:
        raise HTTPException(
            status_code=400,
            detail="Organization and project must be selected."
        )
    
    if not snapshot_id:
        raise HTTPException(
            status_code=400,
            detail="snapshot_id is required in request body."
        )
    
    if not validate_user_access(email, org, project):
        raise HTTPException(
            status_code=403,
            detail=f"User does not have access to org '{org}' / project '{project}'",
        )
    
    # Derive flow identifier: "{org}.{project}.report"
    flow_identifier = f"{org}.{project}.report"
    
    # Update last_accessed_at for this thread (non-blocking)
    try:
        await upsert_thread(thread_id, user_id, title=None, flow=flow_identifier)
    except Exception as e:
        logger.warning(
            "report_thread_tracking_failed",
            thread_id=thread_id,
            user_id=user_id,
            flow=flow_identifier,
            error=str(e),
            error_type=type(e).__name__,
        )
    
    # Extract checkpoint_id from snapshot_id (format: "checkpoint_id:snapshot_seq" or just "snapshot_seq")
    checkpoint_id = None
    if ":" in snapshot_id:
        checkpoint_id = snapshot_id.split(":")[0]
    else:
        # If no checkpoint_id, use thread_id to get latest checkpoint
        # For now, we'll use thread_id as checkpoint_id
        checkpoint_id = thread_id
    
    # Create config with checkpoint_id for restore
    config = {
        "configurable": {
            "thread_id": thread_id,
            "checkpoint_id": checkpoint_id
        }
    }
    
    # Get the report graph instance
    report_graph = get_graph(org, project, "report")
    
    # Stream events from the restored checkpoint
    return StreamingResponse(
        stream_report_events(
            initial_state={},  # Will be restored from checkpoint
            config=config,
            thread_id=thread_id,
            org=org,
            project=project,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{thread_id}/stop")
async def stop_report(
    thread_id: str,
    user_payload: dict = Depends(verify_google_token),
):
    """Stops an ongoing report generation.
    
    Sets cancellation flag so current nodes finish but no new nodes start.
    Works for both streaming mode (local/cloud_run_service) and background task mode.
    For streaming mode, the frontend will also abort the connection.
    """
    logger.info(
        "report_stop_endpoint_called",
        thread_id=thread_id,
        user_id=user_payload.get("sub"),
    )
    
    # Set cancellation flag - checked in event loop between nodes
    _cancelled_threads[thread_id] = True
    
    # Also cancel task for cloud_run_service mode
    task = _active_tasks.get(thread_id)
    if task:
        logger.info(
            "report_task_cancellation_starting",
            thread_id=thread_id,
        )
        task.cancel()
        logger.info(
            "report_task_cancelled",
            thread_id=thread_id,
        )
    else:
        logger.info(
            "report_stop_no_active_task",
            thread_id=thread_id,
        )
    
    logger.info("report_stop_requested", thread_id=thread_id)
    return {"status": "stopping", "message": "Termination signal sent to agent."}

@router.get("/{thread_id}/status")
async def get_status(
    thread_id: str,
    user_payload: dict = Depends(verify_google_token),
    x_org: str | None = Header(None, alias="X-Org"),
    x_project: str | None = Header(None, alias="X-Project"),
):
    """Gets granular status (e.g. 5/10 chapters done)."""
    user_id = user_payload["sub"]
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
    
    # Derive flow identifier: "{org}.{project}.report"
    flow_identifier = f"{org}.{project}.report"
    
    # Update last_accessed_at for this thread (non-blocking)
    try:
        await upsert_thread(thread_id, user_id, title=None, flow=flow_identifier)
    except Exception as e:
        logger.warning(
            "report_thread_tracking_failed",
            thread_id=thread_id,
            user_id=user_id,
            flow=flow_identifier,
            error=str(e),
            error_type=type(e).__name__,
        )
    
    config = {"configurable": {"thread_id": thread_id}}
    
    # Get the report graph instance
    report_graph = get_graph(org, project, "report")
    
    # Check local state
    try:
        snapshot = await asyncio.to_thread(report_graph.get_state, config)
    except Exception:
        return {"status": "not_found"}
    
    if not snapshot.values:
        return {"status": "not_found_or_empty"}
    
    current_values = snapshot.values
    chapters = current_values.get("chapters", [])
    logs = current_values.get("logs", [])
    
    is_complete = "final_report" in current_values
    
    # Extract visited nodes from current snapshot tasks (optimized - no history iteration)
    # This eliminates expensive get_state_history() call that iterates through all checkpoints
    next_nodes = list(snapshot.next) if snapshot.next else []
    visited_nodes = []
    if snapshot.tasks:
        visited_nodes = [t.name for t in snapshot.tasks if hasattr(t, 'name')]

    # Limit logs to last 20 entries to reduce payload size
    recent_logs = logs[-20:] if logs else []

    return {
        "status": "completed" if is_complete else "running",
        "progress": {
            "chapters_completed": len(chapters),
            "recent_logs": recent_logs
        },
        "graph_state": {
            "visited_nodes": visited_nodes,
            "next": next_nodes
        },
        "result": current_values.get("final_report") if is_complete else None
    }

@router.get("/{thread_id}/load")
async def load_report_checkpoint(
    thread_id: str,
    user_payload: dict = Depends(verify_google_token),
    x_org: str | None = Header(None, alias="X-Org"),
    x_project: str | None = Header(None, alias="X-Project"),
):
    """Load the latest checkpoint state for a thread without resuming execution.
    
    Used by frontend to restore UI state on page refresh.
    """
    user_id = user_payload["sub"]
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
            action="load_report_checkpoint",
        )
        raise HTTPException(
            status_code=403,
            detail=f"User does not have access to org '{org}' / project '{project}'",
        )
    
    # Derive flow identifier: "{org}.{project}.report"
    flow_identifier = f"{org}.{project}.report"
    
    # Update last_accessed_at for this thread (non-blocking)
    try:
        await upsert_thread(thread_id, user_id, title=None, flow=flow_identifier)
    except Exception as e:
        logger.warning(
            "report_thread_tracking_failed",
            thread_id=thread_id,
            user_id=user_id,
            flow=flow_identifier,
            error=str(e),
            error_type=type(e).__name__,
        )
    
    config = {"configurable": {"thread_id": thread_id}}
    
    # Get the report graph instance
    report_graph = get_graph(org, project, "report")
    
    # Get latest checkpoint state
    # Use asyncio.to_thread to avoid AsyncPostgresSaver sync call error
    try:
        snapshot = await asyncio.to_thread(report_graph.get_state, config)
    except Exception as e:
        logger.debug(
            "report_checkpoint_not_found",
            thread_id=thread_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        return {"status": "not_found", "state": None}
    
    if not snapshot.values:
        return {"status": "not_found_or_empty", "state": None}
    
    current_values = snapshot.values
    chapters = current_values.get("chapters", [])
    logs = current_values.get("logs", [])
    
    is_complete = "final_report" in current_values
    
    # Get visited nodes from history
    next_nodes = list(snapshot.next) if snapshot.next else []
    visited_nodes = []
    try:
        async for state_item in report_graph.get_state_history(config):
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
        "state": {
            "raw_procedures": current_values.get("raw_procedures", []),
            "pending_clusters": current_values.get("pending_clusters", []),
            "clusters_all": current_values.get("clusters_all"),
            "chapters": chapters,
            "final_report": current_values.get("final_report") if is_complete else None
        },
        "result": current_values.get("final_report") if is_complete else None
    }

@router.get("/{thread_id}/chapters/download")
async def download_chapters(
    thread_id: str,
    user_payload: dict = Depends(verify_google_token),
    x_org: str | None = Header(None, alias="X-Org"),
    x_project: str | None = Header(None, alias="X-Project"),
):
    """Download all chapters as a single DOCX file.
    
    Retrieves chapters from the report state, combines them into a single markdown document,
    converts to DOCX, and returns the file for download.
    """
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
            action="download_chapters",
        )
        raise HTTPException(
            status_code=403,
            detail=f"User does not have access to org '{org}' / project '{project}'",
        )
    
    config = {"configurable": {"thread_id": thread_id}}
    
    # Get the report graph instance
    report_graph = get_graph(org, project, "report")
    
    # Get current state
    try:
        snapshot = await asyncio.to_thread(report_graph.get_state, config)
    except Exception as e:
        logger.debug(
            "report_chapters_download_state_not_found",
            thread_id=thread_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=404,
            detail="Report state not found for this thread."
        )
    
    if not snapshot.values:
        raise HTTPException(
            status_code=404,
            detail="Report state is empty."
        )
    
    # Get chapters from state
    chapters = snapshot.values.get("chapters", [])
    
    if not chapters or len(chapters) == 0:
        raise HTTPException(
            status_code=404,
            detail="No chapters available for download."
        )
    
    try:
        # Combine all chapters into a single markdown document
        # Separate chapters with a horizontal rule
        combined_markdown = "\n\n---\n\n".join(str(chapter) for chapter in chapters)
        
        logger.info(
            "chapters_download_started",
            thread_id=thread_id,
            chapters_count=len(chapters),
            markdown_length=len(combined_markdown),
        )
        
        # Convert markdown to DOCX using pypandoc
        # Use temporary file approach since pypandoc.convert_text doesn't directly return bytes
        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as tmp_file:
            try:
                pypandoc.convert_text(
                    combined_markdown,
                    'docx',
                    format='md',
                    outputfile=tmp_file.name,
                    extra_args=['--standalone'],
                )
                
                # Read the generated DOCX file
                with open(tmp_file.name, 'rb') as f:
                    docx_bytes = f.read()
                
                logger.debug(
                    "chapters_download_conversion_complete",
                    thread_id=thread_id,
                    docx_size=len(docx_bytes),
                )
            finally:
                # Clean up temporary file
                try:
                    os.unlink(tmp_file.name)
                except OSError:
                    pass
        
        # Create a generator function to yield the file content
        def generate():
            yield docx_bytes
        
        # Return the file as a download
        return StreamingResponse(
            generate(),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": 'attachment; filename="chapters.docx"'
            }
        )
        
    except RuntimeError as e:
        # pypandoc raises RuntimeError if pandoc is not installed
        error_msg = f"Pandoc is not available: {str(e)}"
        logger.error(
            "chapters_download_pandoc_error",
            thread_id=thread_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail=error_msg
        )
    except OSError as e:
        # File system errors
        error_msg = f"File system error during conversion: {str(e)}"
        logger.error(
            "chapters_download_filesystem_error",
            thread_id=thread_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail=error_msg
        )
    except Exception as e:
        # Other errors
        error_msg = f"Failed to generate DOCX: {str(e)}"
        logger.exception(
            "chapters_download_failed",
            thread_id=thread_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail=error_msg
        )

@router.get("/{thread_id}/final-report/download")
async def download_final_report(
    thread_id: str,
    user_payload: dict = Depends(verify_google_token),
    x_org: str | None = Header(None, alias="X-Org"),
    x_project: str | None = Header(None, alias="X-Project"),
):
    """Download the final report as a DOCX file.
    
    Retrieves the final report from the report state, converts it to DOCX,
    and returns the file for download.
    """
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
            action="download_final_report",
        )
        raise HTTPException(
            status_code=403,
            detail=f"User does not have access to org '{org}' / project '{project}'",
        )
    
    config = {"configurable": {"thread_id": thread_id}}
    
    # Get the report graph instance
    report_graph = get_graph(org, project, "report")
    
    # Get current state
    try:
        snapshot = await asyncio.to_thread(report_graph.get_state, config)
    except Exception as e:
        logger.debug(
            "report_final_report_download_state_not_found",
            thread_id=thread_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=404,
            detail="Report state not found for this thread."
        )
    
    if not snapshot.values:
        raise HTTPException(
            status_code=404,
            detail="Report state is empty."
        )
    
    # Get final report from state
    final_report = snapshot.values.get("final_report")
    
    if not final_report:
        raise HTTPException(
            status_code=404,
            detail="No final report available for download."
        )
    
    # Log what we found in state
    logger.debug(
        "final_report_download_extracted_from_state",
        thread_id=thread_id,
        final_report_type=type(final_report).__name__,
        is_string=isinstance(final_report, str),
        is_dict=isinstance(final_report, dict),
        final_report_length=len(str(final_report)) if final_report else 0,
    )
    
    # Convert final_report to string if needed
    if isinstance(final_report, str):
        report_markdown = final_report
    elif isinstance(final_report, dict):
        # Try to extract text from object
        report_markdown = final_report.get("text") or final_report.get("content") or str(final_report)
    else:
        report_markdown = str(final_report)
    
    # Warn if report seems unusually short (might indicate truncation)
    if len(report_markdown) < 500:
        logger.warning(
            "final_report_download_short_report",
            thread_id=thread_id,
            markdown_length=len(report_markdown),
            first_500_chars=report_markdown[:500] if len(report_markdown) > 0 else "",
        )
    
    try:
        logger.info(
            "final_report_download_started",
            thread_id=thread_id,
            markdown_length=len(report_markdown),
        )
        
        # Convert markdown to DOCX using pypandoc
        # Use temporary file approach since pypandoc.convert_text doesn't directly return bytes
        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as tmp_file:
            try:
                pypandoc.convert_text(
                    report_markdown,
                    'docx',
                    format='md',
                    outputfile=tmp_file.name,
                    extra_args=['--standalone'],
                )
                
                # Read the generated DOCX file
                with open(tmp_file.name, 'rb') as f:
                    docx_bytes = f.read()
                
                logger.debug(
                    "final_report_download_conversion_complete",
                    thread_id=thread_id,
                    docx_size=len(docx_bytes),
                )
            finally:
                # Clean up temporary file
                try:
                    os.unlink(tmp_file.name)
                except OSError:
                    pass
        
        # Create a generator function to yield the file content
        def generate():
            yield docx_bytes
        
        # Return the file as a download
        return StreamingResponse(
            generate(),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": 'attachment; filename="final_report.docx"'
            }
        )
        
    except RuntimeError as e:
        # pypandoc raises RuntimeError if pandoc is not installed
        error_msg = f"Pandoc is not available: {str(e)}"
        logger.error(
            "final_report_download_pandoc_error",
            thread_id=thread_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail=error_msg
        )
    except Exception as e:
        # Other errors
        error_msg = f"Failed to generate DOCX: {str(e)}"
        logger.exception(
            "final_report_download_failed",
            thread_id=thread_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail=error_msg
        )

@router.post("/{thread_id}/resume")
async def resume_report(
    thread_id: str,
    background_tasks: BackgroundTasks,
    user_payload: dict = Depends(verify_google_token),
    x_org: str | None = Header(None, alias="X-Org"),
    x_project: str | None = Header(None, alias="X-Project"),
):
    """Resumes a stopped/paused workflow from the last checkpoint."""
    user_id = user_payload["sub"]
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
    
    # Derive flow identifier: "{org}.{project}.report"
    flow_identifier = f"{org}.{project}.report"
    
    # Update last_accessed_at for this thread (non-blocking)
    try:
        await upsert_thread(thread_id, user_id, title=None, flow=flow_identifier)
    except Exception as e:
        logger.warning(
            "report_thread_tracking_failed",
            thread_id=thread_id,
            user_id=user_id,
            flow=flow_identifier,
            error=str(e),
            error_type=type(e).__name__,
        )
    
    config = {"configurable": {"thread_id": thread_id}}
    
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
            model = job_params.get("model")
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
        model = payload.get("model")
    
    if not all([thread_id, org, project]):
        raise HTTPException(
            status_code=400,
            detail="Missing required parameters: thread_id, org, project"
        )
    
    # Fetch all procedures from database
    try:
        procedures = _get_all_procedures_raw_sql()
        logger.info(
            "procedures_fetched_from_database",
            thread_id=thread_id,
            procedure_count=len(procedures),
        )
    except Exception as e:
        logger.exception(
            "failed_to_fetch_procedures",
            thread_id=thread_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch procedures from database: {str(e)}"
        )
    
    # Initialize state for new report - clear final_report from any previous run
    initial_state = {
        "raw_procedures": procedures,
        "final_report": "",  # Clear any previous final_report
    }
    model = _resolve_report_model(model)
    config = {
        "configurable": {
            "thread_id": thread_id
        },
        "recursion_limit": CONSTANTS.get("GRAPH_RECURSION_LIMIT", 50),  # Prevent infinite loops
    }
    if model:
        config["configurable"]["model_name"] = model

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
