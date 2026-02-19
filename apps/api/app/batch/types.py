"""
Type definitions and constants for batch operations.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class JobStatus(str, Enum):
    """Status of a batch job execution."""
    
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


@dataclass
class ExecutionMetadata:
    """Metadata for a Cloud Run job execution."""
    
    execution_name: str
    thread_id: str
    org: str
    project: str
    job_name: str
    status: JobStatus = JobStatus.UNKNOWN
    start_time: str | None = None
    end_time: str | None = None
    error_message: str | None = None


# Job name pattern: hit8-report-job-{suffix}
# Suffix is -prd, -stg, or empty for dev
JOB_NAME_PREFIX = "hit8-report-job"
JOB_NAME_PATTERN = f"{JOB_NAME_PREFIX}{{suffix}}"
