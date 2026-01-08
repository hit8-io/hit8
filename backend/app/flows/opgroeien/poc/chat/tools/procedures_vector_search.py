"""
Vector search tool for procedures collection.
"""
from __future__ import annotations

import json
from typing import Any

import structlog
from langchain_core.tools import tool

from app.flows.opgroeien.poc.constants import (
    COLLECTION_PROCEDURES,
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
def procedures_vector_search(query: str) -> str:
    """
    Vector database with internal procedures. Returns extensive metadata, e.g.:
    {"run": 1, "date": "2024-04-18", "file": "PR-JH-06.docx", "titel": "Beslissing toekenning erkenning", "domain": "Jeugdhulp", "folder": "Jeugdhulp/Procedures", "source": "intern", "project": "opgroeien", "doc_type": "regelgeving", "language": "nl", "chunk_size": 1000, "content_type": "markdown", "total_chunks": 13, "chunk_overlap": 200, "chunk_algorithm": "markdown recursive", "embedding_model": "gemini-embedding-001", "embedding_dimension": 1536}
    
    Args:
        query: The search query
        
    Returns:
        JSON string with search results and metadata
    """
    try:
        results = _vector_search_raw_sql(query, COLLECTION_PROCEDURES, k=VECTOR_SEARCH_DEFAULT_K)
        
        if not results:
            logger.warning(
                "procedures_vector_search_empty",
                query=query,
                message="No results found - vector store may be empty",
            )
            return json.dumps({
                "error": "No results found. The procedures vector store appears to be empty. Please populate it with data first.",
                "results": []
            }, ensure_ascii=False)
        
        formatted_results = _format_vector_search_results(results)
        
        logger.info(
            "procedures_vector_search_success",
            query=query,
            result_count=len(formatted_results),
        )
        
        return json.dumps(formatted_results, ensure_ascii=False)
    except Exception as e:
        logger.error(
            "procedures_vector_search_failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        return json.dumps({"error": f"Failed to search procedures: {str(e)}"})
