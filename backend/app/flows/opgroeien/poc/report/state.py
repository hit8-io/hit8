"""
State definition for the Long-Running Report Agent.
"""
from __future__ import annotations

import operator
from typing import Annotated, Dict, List, TypedDict, Any, Optional

from langchain_core.messages import BaseMessage


def merge_dicts(left: Optional[Dict[str, str]], right: Optional[Dict[str, str]]) -> Dict[str, str]:
    """
    Reducer function to merge two dictionaries.
    Handles None values by treating them as empty dictionaries.
    """
    left = left or {}
    right = right or {}
    return {**left, **right}


def merge_cluster_status(
    left: Optional[Dict[str, ClusterStatus]], 
    right: Optional[Dict[str, ClusterStatus]]
) -> Dict[str, ClusterStatus]:
    """
    Reducer function to merge two cluster_status dictionaries.
    Handles None values by treating them as empty dictionaries.
    Preserves retry_count from left (existing state) when right (update) doesn't include it.
    CRITICAL: Auto-increments retry_count when status changes to "failed" (after a retry attempt fails).
    """
    left = left or {}
    right = right or {}
    result = {**left}
    # Merge right into result, but preserve retry_count from left if right doesn't have it
    for file_id, right_status in right.items():
        if file_id in result:
            # Merge status dicts, preserving retry_count from left if not in right
            left_status = result[file_id]
            merged_status = {**left_status, **right_status}
            
            # CRITICAL: If status is changing to "failed", increment retry_count
            # This handles the case where a retry attempt fails (times out)
            left_status_val = left_status.get("status", "")
            right_status_val = right_status.get("status", "")
            
            if right_status_val == "failed" and left_status_val != "failed":
                # Status is changing to "failed" - this is a failure after a retry attempt
                # Increment retry_count (or set to 1 if it doesn't exist)
                current_retry_count = left_status.get("retry_count", 0) or 0
                merged_status["retry_count"] = current_retry_count + 1
            elif right_status_val == "failed" and left_status_val == "failed":
                # Status is already "failed" and being set to "failed" again
                # This can happen with parallel updates or race conditions
                # Only increment if right_status explicitly provides a new retry_count
                # Otherwise preserve the existing retry_count (don't double-increment)
                if "retry_count" in right_status:
                    # Right explicitly set retry_count, use it
                    merged_status["retry_count"] = right_status["retry_count"]
                elif "retry_count" in left_status:
                    # Preserve existing retry_count from left
                    merged_status["retry_count"] = left_status["retry_count"]
                else:
                    # Neither has retry_count, set to 1 (first failure)
                    merged_status["retry_count"] = 1
            elif "retry_count" not in right_status and "retry_count" in left_status:
                # If right doesn't have retry_count, preserve it from left
                merged_status["retry_count"] = left_status["retry_count"]
            
            result[file_id] = merged_status
        else:
            # New entry - if status is "failed", set retry_count to 1 (first failure)
            if right_status.get("status") == "failed":
                right_status = {**right_status, "retry_count": 1}
            result[file_id] = right_status
    return result


class ClusterStatus(TypedDict, total=False):
    """Status information for a single cluster."""
    status: str  # "pending" | "active" | "completed" | "failed"
    started_at: Optional[str]  # ISO timestamp
    ended_at: Optional[str]  # ISO timestamp
    error: Optional[str]  # Error message if status is "failed"
    retry_count: Optional[int]  # Number of retry attempts (to prevent infinite retries)


class ReportState(TypedDict):
    """
    State for the Report Reporting System.
    """
    # Input Data
    raw_procedures: List[Dict[str, Any]]
    
    # Cluster Management
    # Initial full list of all clusters (for UI display)
    clusters_all: Optional[List[Dict[str, Any]]]
    # Status tracking per cluster (file_id -> ClusterStatus)
    # Annotated with merge_cluster_status allows parallel nodes to update this dict concurrently
    cluster_status: Annotated[Optional[Dict[str, ClusterStatus]], merge_cluster_status]
    
    # Batching Support
    # Stores remaining clusters that haven't been processed yet
    # Each cluster is a dict with 'procedures' and 'meta' keys
    pending_clusters: List[Dict[str, Any]]
    # Tracks the number of batches processed (for MAX_BATCHES limit in dev)
    batch_count: Optional[int]
    # Number of analyst completions we have "accounted for" by having sent a batch that is now done
    last_batch_sent_count: Optional[int]
    # Size of the last batch we (or splitter) sent; used to know when we've received all completions
    last_send_size: Optional[int]
    
    # Internal Tracking
    # Annotated with operator.add allows parallel nodes to append to this list
    # logic: each chapter string is appended
    chapters: Annotated[List[str], operator.add]
    # Chapters indexed by file_id for easier lookup
    # Annotated with merge_dicts allows parallel nodes to update this dict concurrently
    chapters_by_file_id: Annotated[Optional[Dict[str, str]], merge_dicts]
    # List of all chapter IDs (file_ids) that were requested at the start
    # Used to detect missing/failed chapters for retry
    requested_chapter_ids: Optional[List[str]]
    # List of chapter IDs that have failed and need retry
    # NOTE: This is set by batch_processor_node, not by individual analyst nodes
    # Individual analyst nodes don't need to track this - batch_processor_node detects failures
    failed_chapter_ids: Optional[List[str]]
    
    # Logs/Events for UI
    logs: Annotated[List[str], operator.add]
    
    # Final Output
    final_report: str
