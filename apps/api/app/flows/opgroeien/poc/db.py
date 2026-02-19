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
    BATCH_TYPE_PROCEDURES,
    BATCH_TYPE_REGELGEVING,
    EMBEDDING_MODEL_NAME,
    EMBEDDING_OUTPUT_DIMENSIONALITY,
    EMBEDDING_PROVIDER,
    EMBEDDING_TASK_TYPE,
    VECTOR_SEARCH_DEFAULT_K,
)
from app import constants
from app.config import settings

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
    "_get_batch_ids_by_type",
    "_get_document_by_key",
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
    # Lazy import to avoid circular dependency
    from app.api.database import get_sync_connection
    return get_sync_connection()


def _get_batch_ids_by_type(
    type: str,
    org: str | None = None,
    project: str | None = None,
) -> list[str]:
    """
    Get all batch IDs for a given type, optionally filtered by org/project.
    
    Args:
        type: Batch type ('proc' or 'regel')
        org: Optional org filter
        project: Optional project filter
        
    Returns:
        List of batch IDs (UUIDs as strings)
    """
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Build WHERE conditions safely
                conditions = [psql.SQL("type = %s")]
                params: list[Any] = [type]
                
                if org is not None:
                    conditions.append(psql.SQL("org = %s"))
                    params.append(org)
                
                if project is not None:
                    conditions.append(psql.SQL("project = %s"))
                    params.append(project)
                
                where_clause = psql.SQL(" AND ").join(conditions)
                
                query_sql = psql.SQL("""
                    SELECT id
                    FROM hit8.batches
                    WHERE {}
                """).format(where_clause)
                
                cursor.execute(query_sql, params)
                batch_ids = [str(row[0]) for row in cursor.fetchall()]
                
                return batch_ids
    except Exception as e:
        logger.error(
            "get_batch_ids_by_type_failed",
            type=type,
            org=org,
            project=project,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise


def _vector_search_raw_sql(  # noqa: PLR0911
    query: str,
    batch_type: str,
    batch_ids: list[str] | None = None,
    k: int = VECTOR_SEARCH_DEFAULT_K,
) -> list[tuple[dict[str, Any], float]]:
    """
    Perform vector similarity search using unified schema with batch filtering.
    
    Note: This function is exported and used by tools.py and tools_future.py.
    
    Args:
        query: The search query text
        batch_type: Batch type ('proc' or 'regel')
        batch_ids: Optional list of batch IDs to filter by. If None, searches all batches of the type.
        k: Number of results to return
        
    Returns:
        List of tuples: (result_dict, score) where result_dict contains:
            - content: The text content
            - metadata: JSON metadata from the database
            - doc: Document identifier (doc_key)
            - chunk: Chunk number (chunk_index)
        Score is cosine similarity (higher is more similar, converted from distance: 1 - distance)
    """
    # Validate batch_type
    allowed_types = {BATCH_TYPE_PROCEDURES, BATCH_TYPE_REGELGEVING}
    if batch_type not in allowed_types:
        raise ValueError(f"Invalid batch_type: {batch_type}. Allowed: {allowed_types}")
    
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
                # Build WHERE clause with batch filtering safely
                where_conditions = [
                    psql.SQL("e.embedding IS NOT NULL"),
                    psql.SQL("e.type = %s"),
                ]
                
                if batch_ids is not None and len(batch_ids) > 0:
                    where_conditions.append(psql.SQL("e.batch_id = ANY(%s)"))
                
                where_clause = psql.SQL(" AND ").join(where_conditions)
                
                # Use cosine distance operator (<=>) and convert to similarity score
                # Join with chunks and documents to get content and doc_key
                # Cosine distance: 0 = identical, 1 = orthogonal, 2 = opposite
                # Similarity: 1 - distance (higher is more similar)
                # Note: SQL parameter order matches placeholder order in SQL string:
                # 1. SELECT vector (%s::vector)
                # 2. WHERE e.type = %s
                # 3. WHERE e.batch_id = ANY(%s) (if provided)
                # 4. ORDER BY vector (%s::vector)
                # 5. LIMIT %s
                query_sql = psql.SQL("""
                    SELECT 
                        c.content,
                        c.metadata,
                        d.doc_key as doc,
                        c.chunk_index as chunk,
                        1 - (e.embedding <=> %s::vector) as similarity_score
                    FROM hit8.embeddings e
                    JOIN hit8.chunks c ON e.chunk_id = c.id
                    JOIN hit8.documents d ON c.document_id = d.id
                    WHERE {}
                    ORDER BY e.embedding <=> %s::vector
                    LIMIT %s
                """).format(where_clause)
                
                # Build parameters in SQL placeholder order:
                # 1. embedding_array (for SELECT vector)
                # 2. batch_type (for WHERE e.type = %s)
                # 3. batch_ids (for WHERE e.batch_id = ANY(%s), if provided)
                # 4. embedding_array (for ORDER BY vector)
                # 5. k (for LIMIT)
                query_params: list[Any] = [embedding_array, batch_type]
                if batch_ids is not None and len(batch_ids) > 0:
                    query_params.append(batch_ids)
                query_params.extend([embedding_array, k])
                
                cursor.execute(query_sql, query_params)
                
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
            batch_type=batch_type,
            batch_ids=batch_ids,
            query=query,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise


def _get_document_by_key(
    batch_id: str,
    doc_key: str,
) -> dict[str, Any] | None:
    """
    Get a document by batch_id and doc_key using unified schema.
    
    Args:
        batch_id: UUID of the batch
        doc_key: Document key identifier (e.g., "PR-AV-02")
        
    Returns:
        Dictionary with keys: doc_key, content, metadata; or None if not found
    """
    # Validate input
    if not doc_key or not doc_key.strip():
        raise ValueError("doc_key parameter cannot be empty")
    if not batch_id or not batch_id.strip():
        raise ValueError("batch_id parameter cannot be empty")
    
    try:
        # Connect to database and execute query (with SSL support for production)
        with _get_db_connection() as conn:
            with conn.cursor() as cursor:
                query_sql = psql.SQL("""
                    SELECT 
                        doc_key,
                        content,
                        metadata
                    FROM hit8.documents
                    WHERE batch_id = %s AND doc_key = %s
                    LIMIT 1
                """)
                
                cursor.execute(query_sql, (batch_id, doc_key))
                
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
            "get_document_by_key_failed",
            batch_id=batch_id,
            doc_key=doc_key,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise


def _get_procedure_raw_sql(doc: str) -> dict[str, Any] | None:
    """
    Get a procedure document by document identifier using unified schema.
    
    Searches across all batches of type 'proc' to find the document.
    
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
                # Search across all batches of type 'proc'
                query_sql = psql.SQL("""
                    SELECT 
                        d.doc_key,
                        d.content,
                        d.metadata
                    FROM hit8.documents d
                    JOIN hit8.batches b ON d.batch_id = b.id
                    WHERE d.doc_key = %s AND d.type = %s
                    LIMIT 1
                """)
                
                cursor.execute(query_sql, (doc, BATCH_TYPE_PROCEDURES))
                
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
    Get a regelgeving document by document identifier using unified schema.
    
    Searches across all batches of type 'regel' to find the document.
    
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
                # Search across all batches of type 'regel'
                query_sql = psql.SQL("""
                    SELECT 
                        d.doc_key,
                        d.content,
                        d.metadata
                    FROM hit8.documents d
                    JOIN hit8.batches b ON d.batch_id = b.id
                    WHERE d.doc_key = %s AND d.type = %s
                    LIMIT 1
                """)
                
                cursor.execute(query_sql, (doc, BATCH_TYPE_REGELGEVING))
                
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
    Get all procedure documents from the database using unified schema.
    
    Searches across all batches of type 'proc'.
    
    Returns:
        List of dictionaries, each with keys: doc, content, metadata
    """
    try:
        # Connect to database and execute query (with SSL support for production)
        with _get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Limit the number of returned procedures if MAX_PROCEDURES_DEV is set
                max_procedures = constants.CONSTANTS.get("MAX_PROCEDURES_DEV")
                
                if max_procedures is not None:
                    query_sql = psql.SQL("""
                        SELECT 
                            d.doc_key,
                            d.content,
                            d.metadata
                        FROM hit8.documents d
                        JOIN hit8.batches b ON d.batch_id = b.id
                        WHERE d.type = %s
                        ORDER BY d.doc_key
                        LIMIT %s
                    """)
                    cursor.execute(query_sql, (BATCH_TYPE_PROCEDURES, max_procedures))
                else:
                    query_sql = psql.SQL("""
                        SELECT 
                            d.doc_key,
                            d.content,
                            d.metadata
                        FROM hit8.documents d
                        JOIN hit8.batches b ON d.batch_id = b.id
                        WHERE d.type = %s
                        ORDER BY d.doc_key
                    """)
                    cursor.execute(query_sql, (BATCH_TYPE_PROCEDURES,))
                
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
