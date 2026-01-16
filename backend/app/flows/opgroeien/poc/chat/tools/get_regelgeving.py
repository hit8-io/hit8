"""
Tool for getting complete regelgeving content by document name.
"""
from __future__ import annotations

import json

import structlog
from langchain_core.tools import tool

from app.flows.opgroeien.poc.db import (
    _get_regelgeving_raw_sql,
)

logger = structlog.get_logger(__name__)


@tool
def get_regelgeving(doc: str) -> str:
    """
    Get the complete content of regelgeving given its name.
    
    Args:
        doc: The regelgeving document name
        
    Returns:
        JSON string with doc, content, and metadata
    """
    try:
        # Get regelgeving by doc name
        result = _get_regelgeving_raw_sql(doc)
        
        if result is None:
            return json.dumps({"error": f"Regelgeving '{doc}' not found"})
        
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        logger.error(
            "get_regelgeving_failed",
            doc=doc,
            error=str(e),
            error_type=type(e).__name__,
        )
        return json.dumps({"error": f"Failed to get regelgeving: {str(e)}"})
