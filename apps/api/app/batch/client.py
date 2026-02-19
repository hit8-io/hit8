"""
Cloud Run Jobs client initialization and management.
"""
from __future__ import annotations

import json
import threading
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from google.cloud.run_v2 import JobsClient

logger = structlog.get_logger(__name__)

# Cloud Run Jobs client (lazy initialization)
_run_jobs_client: JobsClient | None | bool = None
_run_jobs_client_lock = threading.Lock()


def get_jobs_client() -> JobsClient | None:
    """Get or create Cloud Run Jobs client instance.
    
    Returns:
        JobsClient instance if available, None otherwise.
        
    The client is initialized lazily on first call and cached for subsequent calls.
    If initialization fails, returns None and logs the error.
    """
    global _run_jobs_client
    if _run_jobs_client is None:
        with _run_jobs_client_lock:
            if _run_jobs_client is None:
                try:
                    from google.cloud import run_v2
                    from google.oauth2 import service_account
                    from app.config import settings
                    
                    service_account_info = json.loads(settings.VERTEX_SERVICE_ACCOUNT)
                    credentials = service_account.Credentials.from_service_account_info(
                        service_account_info,
                        scopes=["https://www.googleapis.com/auth/cloud-platform"]
                    )
                    _run_jobs_client = run_v2.JobsClient(credentials=credentials)
                    logger.debug("cloud_run_jobs_client_initialized")
                except ImportError:
                    logger.warning(
                        "cloud_run_jobs_client_not_available",
                        reason="google-cloud-run not installed"
                    )
                    _run_jobs_client = False
                except Exception as e:
                    logger.error(
                        "cloud_run_jobs_client_init_failed",
                        error=str(e),
                        error_type=type(e).__name__,
                    )
                    _run_jobs_client = False
    return _run_jobs_client if _run_jobs_client is not False else None
