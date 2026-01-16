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
    """
    left = left or {}
    right = right or {}
    return {**left, **right}


class ClusterStatus(TypedDict, total=False):
    """Status information for a single cluster."""
    status: str  # "pending" | "active" | "completed" | "error"
    started_at: Optional[str]  # ISO timestamp
    ended_at: Optional[str]  # ISO timestamp
    error: Optional[str]  # Error message if status is "error"


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
    
    # Internal Tracking
    # Annotated with operator.add allows parallel nodes to append to this list
    # logic: each chapter string is appended
    chapters: Annotated[List[str], operator.add]
    # Chapters indexed by file_id for easier lookup
    # Annotated with merge_dicts allows parallel nodes to update this dict concurrently
    chapters_by_file_id: Annotated[Optional[Dict[str, str]], merge_dicts]
    
    # Logs/Events for UI
    logs: Annotated[List[str], operator.add]
    
    # Final Output
    final_report: str
