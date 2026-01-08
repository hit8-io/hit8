"""
Vector search tool for regelgeving collection.
"""
from __future__ import annotations

import json
from typing import Any

import structlog
from langchain_core.tools import tool

from app.flows.opgroeien.poc.constants import (
    COLLECTION_REGELGEVING,
    VECTOR_SEARCH_DEFAULT_K,
)
from app.flows.opgroeien.poc.chat.tools.utils import (
    _vector_search_raw_sql,
)

logger = structlog.get_logger(__name__)


def _format_vector_search_results(
    results: list[tuple[dict[str, Any], float]],
) -> list[dict[str, Any]]:
    """
    Format vector search results into a consistent structure.
    
    Args:
        results: List of (result_dict, score) tuples from vector search
        
    Returns:
        List of formatted result dictionaries with content, score, and optional metadata
    """
    formatted_results = []
    for result_dict, score in results:
        formatted_result = {
            "content": result_dict.get("content", ""),
            "score": score,
        }
        # Add metadata if available
        if result_dict.get("metadata"):
            formatted_result["metadata"] = result_dict["metadata"]
        formatted_results.append(formatted_result)
    return formatted_results


@tool
def regelgeving_vector_search(query: str) -> str:
    """
    Vector database with all applicable official regulations.
    
    Args:
        query: The search query
        
    Returns:
        JSON string with search results
    """
    try:
        results = _vector_search_raw_sql(query, COLLECTION_REGELGEVING, k=VECTOR_SEARCH_DEFAULT_K)
        
        if not results:
            logger.warning(
                "regelgeving_vector_search_empty",
                query=query,
                message="No results found - vector store may be empty",
            )
            return json.dumps({
                "error": "No results found. The regelgeving vector store appears to be empty. Please populate it with data first.",
                "results": []
            }, ensure_ascii=False)
        
        formatted_results = _format_vector_search_results(results)
        
        logger.info(
            "regelgeving_vector_search_success",
            query=query,
            result_count=len(formatted_results),
        )
        
        return json.dumps(formatted_results, ensure_ascii=False)
    except Exception as e:
        logger.error(
            "regelgeving_vector_search_failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        return json.dumps({"error": f"Failed to search regelgeving: {str(e)}"})
