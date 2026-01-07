"""
LangChain tools for the opgroeien agent.
"""
from __future__ import annotations

import json
from typing import Any

import structlog
from langchain_core.tools import tool

from app.flows.opgroeien.poc.constants import (
    COLLECTION_PROCEDURES,
    COLLECTION_REGELGEVING,
    VECTOR_SEARCH_DEFAULT_K,
)
from app.flows.opgroeien.poc.chat.tools_utils import (
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


def _vector_search_tool(
    query: str,
    collection: str,
    collection_display_name: str,
    log_prefix: str,
    k: int = VECTOR_SEARCH_DEFAULT_K,
) -> str:
    """
    Generic vector search tool implementation.
    
    Args:
        query: The search query
        collection: Collection name constant
        collection_display_name: Display name for error messages
        log_prefix: Prefix for log event names
        k: Number of results to return
        
    Returns:
        JSON string with search results and metadata
    """
    try:
        results = _vector_search_raw_sql(query, collection, k=k)
        
        if not results:
            logger.warning(
                f"{log_prefix}_empty",
                query=query,
                message="No results found - vector store may be empty",
            )
            return json.dumps({
                "error": f"No results found. The {collection_display_name} vector store appears to be empty. Please populate it with data first.",
                "results": []
            }, ensure_ascii=False)
        
        formatted_results = _format_vector_search_results(results)
        
        logger.info(
            f"{log_prefix}_success",
            query=query,
            result_count=len(formatted_results),
        )
        
        return json.dumps(formatted_results, ensure_ascii=False)
    except Exception as e:
        logger.error(
            f"{log_prefix}_failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        return json.dumps({"error": f"Failed to search {collection_display_name}: {str(e)}"})


@tool
def procedures_vector_search(query: str) -> str:
    """
    Vector database met interne procedures. Je krijgt uitgebreide metadata terug, bv.:
    {"run": 1, "date": "2024-04-18", "file": "PR-JH-06.docx", "titel": "Beslissing toekenning erkenning", "domain": "Jeugdhulp", "folder": "Jeugdhulp/Procedures", "source": "intern", "project": "opgroeien", "doc_type": "regelgeving", "language": "nl", "chunk_size": 1000, "content_type": "markdown", "total_chunks": 13, "chunk_overlap": 200, "chunk_algorithm": "markdown recursive", "embedding_model": "gemini-embedding-001", "embedding_dimension": 1536}
    
    Args:
        query: The search query
        
    Returns:
        JSON string with search results and metadata
    """
    return _vector_search_tool(
        query=query,
        collection=COLLECTION_PROCEDURES,
        collection_display_name="procedures",
        log_prefix="procedures_vector_search",
    )


@tool
def regelgeving_vector_search(query: str) -> str:
    """
    Vector database met alle toepasbare officiële regelgeving
    
    Args:
        query: The search query
        
    Returns:
        JSON string with search results
    """
    return _vector_search_tool(
        query=query,
        collection=COLLECTION_REGELGEVING,
        collection_display_name="regelgeving",
        log_prefix="regelgeving_vector_search",
    )


def get_all_tools() -> list[Any]:
    """
    Get all active tools for the agent.
    
    To enable additional tools from tools_future.py, import them and add to this list.
    """
    return [
        procedures_vector_search,
        regelgeving_vector_search,
        # Future tools available in tools_future.py:
        # from app.flows.opgroeien.poc.chat.tools_future import (
        #     fetch_webpage,
        #     generate_docx,
        #     generate_xlsx,
        #     extract_entities,
        #     query_knowledge_graph,
        #     get_procedure,
        #     get_regelgeving,
        # )
    ]
