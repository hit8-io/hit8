"""
CLI entry point for Cloud Run batch job execution.

This module is called by Cloud Run Job containers to execute report generation.
It reads job parameters from environment variables and executes the report graph.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

import structlog

# Initialize logging early
from app.logging import configure_structlog, setup_logging

configure_structlog()
setup_logging()
logger = structlog.get_logger(__name__)


def _check_cancellation(thread_id: str) -> bool:
    """Check if execution has been cancelled.
    
    Args:
        thread_id: Thread ID to check.
        
    Returns:
        True if cancelled, False otherwise.
    """
    # Import here to avoid circular dependencies
    try:
        from app.api.routes.report import _cancelled_threads
        return _cancelled_threads.get(thread_id, False)
    except ImportError:
        # If routes module not available, assume not cancelled
        return False


async def _run_report_job() -> int:
    """Execute report job from environment variables.
    
    Returns:
        Exit code: 0 for success, non-zero for failure.
    """
    # Get job parameters from environment
    job_params_env = os.getenv("REPORT_JOB_PARAMS")
    if not job_params_env:
        logger.error("missing_report_job_params")
        return 1
    
    try:
        job_params = json.loads(job_params_env)
        thread_id = job_params.get("thread_id")
        org = job_params.get("org")
        project = job_params.get("project")
        model = job_params.get("model")
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(
            "invalid_report_job_params",
            error=str(e),
            error_type=type(e).__name__,
        )
        return 1
    
    if not all([thread_id, org, project]):
        logger.error(
            "missing_required_params",
            thread_id=thread_id,
            org=org,
            project=project,
        )
        return 1
    
    logger.info(
        "report_job_cli_started",
        thread_id=thread_id,
        org=org,
        project=project,
        model=model,
    )
    
    # Use shared lifecycle (same as FastAPI)
    from app.api.lifecycle import shutdown, startup

    try:
        await startup()

        # Import after init so anything that touches DB/checkpointer is safe
        from app.api.report_execution import prepare_report_execution, execute_report_graph

        initial_state, config, graph = await prepare_report_execution(
            thread_id=thread_id,
            org=org,
            project=project,
            model=model,
        )

        if _check_cancellation(thread_id):
            logger.info("report_job_cancelled_before_start", thread_id=thread_id)
            return 130

        final_state = await execute_report_graph(
            graph=graph,
            initial_state=initial_state,
            config=config,
            thread_id=thread_id,
            org=org,
            project=project,
        )

        logger.info("report_job_cli_completed", thread_id=thread_id, has_final_report="final_report" in final_state)
        return 0

    except KeyboardInterrupt:
        logger.info("report_job_cli_interrupted", thread_id=thread_id)
        return 130
    except Exception as e:
        logger.exception("report_job_cli_failed", thread_id=thread_id, error=str(e), error_type=type(e).__name__)
        return 1
    finally:
        await shutdown()


def main() -> int:
    """Main entry point for CLI.
    
    Returns:
        Exit code: 0 for success, non-zero for failure.
    """
    try:
        return asyncio.run(_run_report_job())
    except KeyboardInterrupt:
        logger.info("report_job_cli_keyboard_interrupt")
        return 130
    except Exception as e:
        logger.exception(
            "report_job_cli_unexpected_error",
            error=str(e),
            error_type=type(e).__name__,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
