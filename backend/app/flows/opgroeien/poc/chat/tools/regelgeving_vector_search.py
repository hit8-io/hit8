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
        List of formatted result dictionaries with content, score, doc, and optional metadata
    """
    formatted_results = []
    for result_dict, score in results:
        formatted_result = {
            "content": result_dict.get("content", ""),
            "score": score,
        }
        # Add doc (document identifier) if available - this is critical for referencing documents
        if result_dict.get("doc"):
            formatted_result["doc"] = result_dict["doc"]
        # Add metadata if available
        if result_dict.get("metadata"):
            formatted_result["metadata"] = result_dict["metadata"]
        formatted_results.append(formatted_result)
    return formatted_results


@tool
def regelgeving_vector_search(query: str) -> str:
    """
    Vector database with all applicable official regulations. Returns results with:
    - content: The regulation content text
    - doc: Document identifier - USE THIS for citations
    - score: Similarity score
    - metadata: JSON object with additional info including:
      * "titel": Document title
      * "date": Document date
      * "file": Original filename
      * Other fields as available
    
    IMPORTANT: Always use the "doc" field for document citations in the format: [Interne Bron: Titel, Document ID, Datum]
    The "doc" field contains the document identifier needed for proper citation.
    
    Args:
        query: The search query
        
    Returns:
        JSON string with search results containing content, doc, score, and metadata
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
        
        # Truncate large content fields to prevent token limit issues
        # Limit per result to keep total output manageable (40 results × 5k = 200k chars max)
        MAX_CONTENT_LENGTH = 5_000  # Max characters per result content
        for result in formatted_results:
            content = result.get("content", "")
            if len(content) > MAX_CONTENT_LENGTH:
                truncated = content[:MAX_CONTENT_LENGTH]
                # Try to cut at newline
                last_newline = truncated.rfind('\n')
                if last_newline > MAX_CONTENT_LENGTH * 0.9:
                    truncated = content[:last_newline]
                result["content"] = truncated + f"\n\n[Content truncated: showing first {len(truncated):,} of {len(content):,} characters]"
        
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
