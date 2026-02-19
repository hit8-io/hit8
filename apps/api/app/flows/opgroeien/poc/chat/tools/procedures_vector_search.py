"""
Vector search tool for procedures collection.
"""
from __future__ import annotations

import json
from typing import Any

import structlog
from langchain_core.tools import tool

from app.flows.opgroeien.poc.constants import (
    BATCH_TYPE_PROCEDURES,
    VECTOR_SEARCH_DEFAULT_K,
)
from app.flows.opgroeien.poc.db import (
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
        # Add doc (document identifier) if available - this is critical for referencing procedures
        if result_dict.get("doc"):
            formatted_result["doc"] = result_dict["doc"]
        # Add metadata if available
        if result_dict.get("metadata"):
            formatted_result["metadata"] = result_dict["metadata"]
        formatted_results.append(formatted_result)
    return formatted_results


@tool
def procedures_vector_search(query: str) -> str:
    """
    Vector database with internal procedures. Returns results with:
    - content: The procedure content text
    - doc: Document identifier (e.g., "PR-AV-02", "PR-JH-06") - USE THIS for citations
    - score: Similarity score
    - metadata: JSON object with additional info including:
      * "titel": Document title
      * "date": Document date
      * "file": Original filename
      * Other fields as available
    
    IMPORTANT: Always use the "doc" field for document citations in the format: [Interne Bron: Titel, Document ID, Datum]
    The "doc" field contains the document identifier needed for proper citation.
    
    Example result structure:
    [
      {
        "content": "...",
        "doc": "PR-AV-02",
        "score": 0.85,
        "metadata": {
          "titel": "Procedure titel",
          "date": "2024-04-18",
          "file": "PR-AV-02.docx"
        }
      }
    ]
    
    Args:
        query: The search query
        
    Returns:
        JSON string with search results containing content, doc, score, and metadata
    """
    logger.debug(
        "debug_vector_search_start",
        query=query,
        type=BATCH_TYPE_PROCEDURES,
    )
    
    try:
        # Search across all batches of type 'proc' (batch_ids=None means search all)
        results = _vector_search_raw_sql(
            query=query,
            batch_type=BATCH_TYPE_PROCEDURES,
            batch_ids=None,  # Search all batches of this type
            k=VECTOR_SEARCH_DEFAULT_K,
        )
        
        logger.debug(
            "debug_vector_search_completed",
            result_count=len(results) if results else 0,
            has_results=results is not None and len(results) > 0,
            sample_raw_result_doc=results[0][0].get("doc") if results and len(results) > 0 else None,
        )
        
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
        
        logger.debug(
            "debug_formatted_results_check",
            result_count=len(formatted_results),
            has_doc_fields=[r.get("doc") is not None for r in formatted_results],
            doc_values=[r.get("doc") for r in formatted_results[:3]],  # First 3 doc values
            sample_result_keys=list(formatted_results[0].keys()) if formatted_results else None,
            sample_result_doc=formatted_results[0].get("doc") if formatted_results else None,
        )
        
        logger.info(
            "procedures_vector_search_success",
            query=query,
            result_count=len(formatted_results),
        )
        
        json_output = json.dumps(formatted_results, ensure_ascii=False)
        
        logger.debug(
            "debug_json_output_ready",
            json_length=len(json_output),
            json_preview=json_output[:500] if len(json_output) > 500 else json_output,
        )
        
        return json_output
    except Exception as e:
        logger.debug(
            "debug_vector_search_exception",
            error=str(e),
            error_type=type(e).__name__,
        )
        logger.error(
            "procedures_vector_search_failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        return json.dumps({"error": f"Failed to search procedures: {str(e)}"})
