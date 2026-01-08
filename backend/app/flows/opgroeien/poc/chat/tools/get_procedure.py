"""
Tool for getting complete procedure content by document name.
"""
from __future__ import annotations

import json

import structlog
from langchain_core.tools import tool

from app.flows.opgroeien.poc.chat.tools.utils import (
    _get_procedure_raw_sql,
)

logger = structlog.get_logger(__name__)


@tool
def get_procedure(doc: str) -> str:
    """
    Get the complete content of a procedure given its name as parameters. A name is e.g. "PR-AV-02".
    
    Return:
    - doc (equals name of the procedure)
    - content
    - metadata (json with all metadata)
    
    Args:
        doc: The procedure name (e.g., "PR-AV-02")
        
    Returns:
        JSON string with doc, content, and metadata
    """
    try:
        # Get procedure by doc name
        result = _get_procedure_raw_sql(doc)
        
        if result is None:
            return json.dumps({"error": f"Procedure '{doc}' not found"})
        
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        logger.error(
            "get_procedure_failed",
            doc=doc,
            error=str(e),
            error_type=type(e).__name__,
        )
        return json.dumps({"error": f"Failed to get procedure: {str(e)}"})
