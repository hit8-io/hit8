"""
CLI entry point for Cloud Run batch job execution.

This module is called by Cloud Run Job containers to execute report generation.
It reads job parameters from environment variables and executes the report graph.
"""
from __future__ import annotations

# VERY TOP: Undeniable debug print before any imports
import sys
print("BOOT: run_report_job imported", file=sys.stderr, flush=True)

import asyncio
import json
import os

import structlog

# Initialize logging early
from app.logging import configure_structlog, setup_logging

# Configure structlog with error handling
try:
    configure_structlog()
    print("BOOT: structlog configured", file=sys.stderr, flush=True)
except Exception as e:
    print(f"BOOT: structlog configuration failed: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
    import traceback
    traceback.print_exc(file=sys.stderr)
    # Continue anyway - we'll use basic logging

# setup_logging() configures handlers to stdout/stderr (good for Cloud Run Jobs)
# For Cloud Run Jobs, we want stdout/stderr only, not Cloud Logging API
try:
    setup_logging()
    print("BOOT: logging setup complete", file=sys.stderr, flush=True)
except Exception as e:
    # Log to stderr as fallback if setup_logging fails
    print(f"BOOT: Failed to setup logging: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
    import traceback
    traceback.print_exc(file=sys.stderr)
    # Continue anyway - structlog is already configured

logger = structlog.get_logger(__name__)
print("BOOT: logger created", file=sys.stderr, flush=True)


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
    print("BOOT: _run_report_job() called", file=sys.stderr, flush=True)
    
    # Get job parameters from environment
    job_params_env = os.getenv("REPORT_JOB_PARAMS")
    if not job_params_env:
        print("ERROR: missing_report_job_params", file=sys.stderr, flush=True)
        try:
            logger.error("missing_report_job_params")
        except Exception:
            pass
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
        logger.info("report_job_starting_initialization", thread_id=thread_id)
        await startup()
        logger.info("report_job_initialization_complete", thread_id=thread_id)

        # Import after init so anything that touches DB/checkpointer is safe
        from app.api.report_execution import prepare_report_execution, execute_report_graph

        logger.info("report_job_preparing_execution", thread_id=thread_id)
        initial_state, config, graph = await prepare_report_execution(
            thread_id=thread_id,
            org=org,
            project=project,
            model=model,
        )
        logger.info("report_job_execution_prepared", thread_id=thread_id)

        if _check_cancellation(thread_id):
            logger.info("report_job_cancelled_before_start", thread_id=thread_id)
            return 130

        logger.info("report_job_starting_graph_execution", thread_id=thread_id)
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
        # Log to both structlog and stderr as fallback
        import traceback
        import sys
        logger.exception("report_job_cli_failed", thread_id=thread_id, error=str(e), error_type=type(e).__name__)
        # Also print to stderr as fallback in case logging isn't working
        print(f"ERROR: report_job_cli_failed: {type(e).__name__}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 1
    finally:
        try:
            logger.info("report_job_starting_cleanup", thread_id=thread_id)
            await shutdown()
            logger.info("report_job_cleanup_complete", thread_id=thread_id)
        except Exception as cleanup_error:
            # Log cleanup errors but don't fail the job because of them
            logger.exception("report_job_cleanup_failed", thread_id=thread_id, error=str(cleanup_error), error_type=type(cleanup_error).__name__)


def main() -> int:
    """Main entry point for CLI.
    
    Returns:
        Exit code: 0 for success, non-zero for failure.
    """
    print("BOOT: main() called", file=sys.stderr, flush=True)
    try:
        print("BOOT: starting asyncio.run(_run_report_job())", file=sys.stderr, flush=True)
        return asyncio.run(_run_report_job())
    except KeyboardInterrupt:
        print("BOOT: KeyboardInterrupt in main()", file=sys.stderr, flush=True)
        try:
            logger.info("report_job_cli_keyboard_interrupt")
        except Exception:
            pass
        return 130
    except Exception as e:
        print(f"BOOT: Unexpected error in main(): {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        import traceback
        traceback.print_exc(file=sys.stderr)
        try:
            logger.exception(
                "report_job_cli_unexpected_error",
                error=str(e),
                error_type=type(e).__name__,
            )
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
