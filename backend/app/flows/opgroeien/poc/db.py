"""
Shared database functions for opgroeien POC flows (chat and report).
"""
from __future__ import annotations

import json
import math
import time
from typing import Any

import structlog
from psycopg import sql as psql
from google.oauth2 import service_account
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.flows.opgroeien.poc.constants import (
    COLLECTION_PROCEDURES,
    COLLECTION_REGELGEVING,
    EMBEDDING_MODEL_NAME,
    EMBEDDING_OUTPUT_DIMENSIONALITY,
    EMBEDDING_PROVIDER,
    EMBEDDING_TASK_TYPE,
    VECTOR_SEARCH_DEFAULT_K,
)
from app import constants
from app.config import settings
from app.api.database import get_sync_connection

logger = structlog.get_logger(__name__)

# Cache embedding model
_embedding_model: GoogleGenerativeAIEmbeddings | None = None

# Exported functions (used by other modules)
__all__ = [
    "_vector_search_raw_sql",
    "_get_procedure_raw_sql",
    "_get_regelgeving_raw_sql",
    "_get_all_procedures_raw_sql",
    "_get_db_connection",
]


def _normalize_vector(vector: list[float]) -> list[float]:
    """
    Normalize a vector using L2 normalization.
    
    Args:
        vector: The vector to normalize
        
    Returns:
        Normalized vector (same length)
    """
    norm = math.sqrt(sum(x * x for x in vector))
    if norm > 0:
        return [x / norm for x in vector]
    return vector


def _format_embedding_for_postgres(embedding: list[float]) -> str:
    """
    Convert embedding list to PostgreSQL array format.
    
    Args:
        embedding: List of float values
        
    Returns:
        PostgreSQL array string format: "[1.0,2.0,3.0]"
    """
    return "[" + ",".join(str(x) for x in embedding) + "]"


def _get_embedding_model() -> GoogleGenerativeAIEmbeddings:
    """Get or create cached embedding model."""
    global _embedding_model
    if _embedding_model is None:
        service_account_info = json.loads(settings.VERTEX_SERVICE_ACCOUNT)
        project_id = service_account_info["project_id"]        
        creds = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=['https://www.googleapis.com/auth/cloud-platform']
        )
        
        _embedding_model = GoogleGenerativeAIEmbeddings(
            model=EMBEDDING_MODEL_NAME,
            task_type=EMBEDDING_TASK_TYPE,
            output_dimensionality=EMBEDDING_OUTPUT_DIMENSIONALITY,
            model_kwargs={"provider": EMBEDDING_PROVIDER},
            project=project_id,
            location=settings.VERTEX_AI_LOCATION or "europe-west1",  # Fallback for backward compatibility
            credentials=creds,
        )
    return _embedding_model


def _parse_metadata(metadata: str | dict[str, Any] | None) -> dict[str, Any]:
    """
    Parse metadata from database, handling string, dict, or None values.
    
    Args:
        metadata: Metadata value from database (can be JSON string, dict, or None)
        
    Returns:
        Parsed metadata dictionary (empty dict if parsing fails or None)
    """
    if isinstance(metadata, str):
        try:
            return json.loads(metadata)
        except json.JSONDecodeError:
            return {}
    elif metadata is None:
        return {}
    return metadata


def _get_db_connection():
    """
    Get database connection with SSL support for production Supabase.
    
    Uses the centralized database connection utility from app.api.database.
    
    - Dev: No SSL (plain connection)
    - Production: SSL with certificate verification (required)
    
    Returns:
        psycopg.Connection: Database connection
    """
    return get_sync_connection()


def _vector_search_raw_sql(  # noqa: PLR0911
    query: str,
    table_name: str,
    k: int = VECTOR_SEARCH_DEFAULT_K,
) -> list[tuple[dict[str, Any], float]]:
    """
    Perform vector similarity search using raw SQL queries on custom tables.
    
    Note: This function is exported and used by tools.py and tools_future.py.
    
    Args:
        query: The search query text
        table_name: Name of the table to search (e.g., 'embeddings_proc' or 'embeddings_regel')
        k: Number of results to return
        
    Returns:
        List of tuples: (result_dict, score) where result_dict contains:
            - content: The text content
            - metadata: JSON metadata from the database
            - doc: Document identifier
            - chunk: Chunk number
        Score is cosine similarity (higher is more similar, converted from distance: 1 - distance)
    """
    # Validate table name to prevent SQL injection
    allowed_tables = {COLLECTION_PROCEDURES, COLLECTION_REGELGEVING}
    if table_name not in allowed_tables:
        raise ValueError(f"Invalid table name: {table_name}. Allowed: {allowed_tables}")
    
    try:
        # Get query embedding with timing
        embedding_model = _get_embedding_model()
        model_name = EMBEDDING_MODEL_NAME
        
        start_time = time.perf_counter()
        query_embedding = embedding_model.embed_query(query)
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        
        # Estimate input tokens (rough approximation: ~4 characters per token)
        input_tokens = len(query) // 4
        
        # Record embedding usage metrics
        try:
            from app.api.observability import record_embedding_usage
            record_embedding_usage(
                model=model_name,
                input_tokens=input_tokens,
                output_tokens=0,  # Embeddings don't have output tokens
                duration_ms=duration_ms,
            )
        except Exception:
            # Don't fail if observability is not available
            pass
        
        # Verify dimension matches expected
        if len(query_embedding) != EMBEDDING_OUTPUT_DIMENSIONALITY:
            logger.warning(
                "embedding_dimension_mismatch",
                expected_dim=EMBEDDING_OUTPUT_DIMENSIONALITY,
                actual_dim=len(query_embedding),
            )
        
        # Normalize the vector for cosine similarity
        query_embedding = _normalize_vector(query_embedding)
        
        # Convert to PostgreSQL array format
        embedding_array = _format_embedding_for_postgres(query_embedding)
        
        # Connect to database and execute query (with SSL support for production)
        with _get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Use cosine distance operator (<=>) and convert to similarity score
                # Cosine distance: 0 = identical, 1 = orthogonal, 2 = opposite
                # Similarity: 1 - distance (higher is more similar)
                # Use psycopg.sql to safely compose SQL with identifiers
                # This properly quotes and escapes the table name, preventing SQL injection
                query_sql = psql.SQL("""
                    SELECT 
                        content,
                        metadata,
                        doc,
                        chunk,
                        1 - (embedding <=> %s::vector) as similarity_score
                    FROM {table}
                    WHERE embedding IS NOT NULL
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                """).format(table=psql.Identifier(table_name))
                
                cursor.execute(query_sql, (embedding_array, embedding_array, k))
                
                # Parse results
                results = []
                for row in cursor.fetchall():
                    content, metadata, doc, chunk, score = row
                    
                    result_dict = {
                        "content": content or "",
                        "metadata": _parse_metadata(metadata),
                        "doc": doc,
                        "chunk": chunk,
                    }
                    results.append((result_dict, float(score)))
                
                return results
                
    except Exception as e:
        logger.error(
            "vector_search_raw_sql_failed",
            table_name=table_name,
            query=query,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise


def _get_procedure_raw_sql(doc: str) -> dict[str, Any] | None:
    """
    Get a procedure document by document identifier using raw SQL query.
    
    Args:
        doc: The document identifier (e.g., "PR-AV-02")
        
    Returns:
        Dictionary with keys: doc, content, metadata; or None if not found
    """
    # Validate input
    if not doc or not doc.strip():
        raise ValueError("doc parameter cannot be empty")
    
    try:
        # Connect to database and execute query (with SSL support for production)
        with _get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Use psycopg.sql to safely compose SQL with identifiers
                # This properly quotes and escapes the table name, preventing SQL injection
                query_sql = psql.SQL("""
                    SELECT 
                        doc,
                        content,
                        metadata
                    FROM {table}
                    WHERE doc = %s
                    LIMIT 1
                """).format(table=psql.Identifier("documents_proc"))
                
                cursor.execute(query_sql, (doc,))
                
                # Fetch result (0 or 1 row)
                row = cursor.fetchone()
                
                if row is None:
                    return None
                
                doc_id, content, metadata = row
                
                result_dict = {
                    "doc": doc_id,
                    "content": content or "",
                    "metadata": _parse_metadata(metadata),
                }
                
                return result_dict
                
    except Exception as e:
        logger.error(
            "get_procedure_raw_sql_failed",
            doc=doc,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise


def _get_regelgeving_raw_sql(doc: str) -> dict[str, Any] | None:
    """
    Get a regelgeving document by document identifier using raw SQL query.
    
    Args:
        doc: The document identifier
        
    Returns:
        Dictionary with keys: doc, content, metadata; or None if not found
    """
    # Validate input
    if not doc or not doc.strip():
        raise ValueError("doc parameter cannot be empty")
    
    try:
        # Connect to database and execute query (with SSL support for production)
        with _get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Use psycopg.sql to safely compose SQL with identifiers
                # This properly quotes and escapes the table name, preventing SQL injection
                query_sql = psql.SQL("""
                    SELECT 
                        doc,
                        content,
                        metadata
                    FROM {table}
                    WHERE doc = %s
                    LIMIT 1
                """).format(table=psql.Identifier("documents_regel"))
                
                cursor.execute(query_sql, (doc,))
                
                # Fetch result (0 or 1 row)
                row = cursor.fetchone()
                
                if row is None:
                    return None
                
                doc_id, content, metadata = row
                
                result_dict = {
                    "doc": doc_id,
                    "content": content or "",
                    "metadata": _parse_metadata(metadata),
                }
                
                return result_dict
                
    except Exception as e:
        logger.error(
            "get_regelgeving_raw_sql_failed",
            doc=doc,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise


def _get_all_procedures_raw_sql() -> list[dict[str, Any]]:
    """
    Get all procedure documents from the database.
    
    Returns:
        List of dictionaries, each with keys: doc, content, metadata
    """
    try:
        # Connect to database and execute query (with SSL support for production)
        with _get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Use psycopg.sql to safely compose SQL with identifiers
                # This properly quotes and escapes the table name, preventing SQL injection
                # Limit the number of returned procedures if MAX_PROCEDURES_DEV is set
                max_procedures = constants.CONSTANTS.get("MAX_PROCEDURES_DEV")
                
                if max_procedures is not None:
                    query_sql = psql.SQL("""
                        SELECT 
                            doc,
                            content,
                            metadata
                        FROM {table}
                        ORDER BY doc
                        LIMIT {limit}
                    """).format(
                        table=psql.Identifier("documents_proc"),
                        limit=psql.Literal(max_procedures),
                    )
                else:
                    query_sql = psql.SQL("""
                        SELECT 
                            doc,
                            content,
                            metadata
                        FROM {table}
                        ORDER BY doc
                    """).format(
                        table=psql.Identifier("documents_proc"),
                    )
                
                cursor.execute(query_sql)
                
                # Fetch all results
                results = []
                for row in cursor.fetchall():
                    doc_id, content, metadata = row
                    
                    result_dict = {
                        "doc": doc_id,
                        "content": content or "",
                        "metadata": _parse_metadata(metadata),
                    }
                    results.append(result_dict)
                
                return results
                
    except Exception as e:
        logger.error(
            "get_all_procedures_raw_sql_failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        raise
