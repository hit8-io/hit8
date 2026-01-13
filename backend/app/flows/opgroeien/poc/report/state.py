"""
State definition for the Long-Running Report Agent.
"""
from __future__ import annotations

import operator
from typing import Annotated, Dict, List, TypedDict, Any

from langchain_core.messages import BaseMessage


class ReportState(TypedDict):
    """
    State for the Report Reporting System.
    """
    # Input Data
    raw_procedures: List[Dict[str, Any]]
    
    # Batching Support
    # Stores remaining clusters that haven't been processed yet
    # Each cluster is a dict with 'procedures' and 'meta' keys
    pending_clusters: List[Dict[str, Any]]
    
    # Internal Tracking
    # Annotated with operator.add allows parallel nodes to append to this list
    # logic: each chapter string is appended
    chapters: Annotated[List[str], operator.add]
    
    # Logs/Events for UI
    logs: Annotated[List[str], operator.add]
    
    # Final Output
    final_report: str
