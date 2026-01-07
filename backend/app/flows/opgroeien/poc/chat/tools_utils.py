"""
Utility functions for the opgroeien agent - vector stores and embeddings.
"""
from __future__ import annotations

# Exported functions (used by other modules)
__all__ = ["_vector_search_raw_sql", "create_tool_node"]

import json
import math
import os
import tempfile
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

import psycopg
from psycopg import sql as psql
import structlog
from google.oauth2 import service_account
from langchain_core.messages import ToolMessage
from langchain_google_genai import GoogleGenerativeAIEmbeddings

if TYPE_CHECKING:
    from app.flows.opgroeien.poc.chat.graph import AgentState

from app.flows.opgroeien.poc.constants import (
    COLLECTION_PROCEDURES,
    COLLECTION_REGELGEVING,
    EMBEDDING_MODEL_NAME,
    EMBEDDING_OUTPUT_DIMENSIONALITY,
    EMBEDDING_PROVIDER,
    EMBEDDING_TASK_TYPE,
    VECTOR_SEARCH_DEFAULT_K,
)
from app.config import settings
from app import constants

logger = structlog.get_logger(__name__)

# Cache embedding model
_embedding_model: GoogleGenerativeAIEmbeddings | None = None

# Cache SSL certificate file path (written from certificate content)
_ssl_cert_file_path: str | None = None
_ssl_cert_lock = threading.Lock()


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
            location=settings.VERTEX_AI_LOCATION,
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


def _get_ssl_cert_file_path() -> str:
    """
    Write SSL certificate content to a temporary file and return the path.
    
    The certificate content is cached in a file that persists for the lifetime
    of the process. This is necessary because psycopg3 requires a file path
    for SSL certificate verification.
    
    Returns:
        str: Path to the certificate file
    """
    global _ssl_cert_file_path
    
    if _ssl_cert_file_path is not None and os.path.exists(_ssl_cert_file_path):
        return _ssl_cert_file_path
    
    with _ssl_cert_lock:
        # Double-check after acquiring lock
        if _ssl_cert_file_path is not None and os.path.exists(_ssl_cert_file_path):
            return _ssl_cert_file_path
        
        # Safety check: certificate content must be provided
        if not settings.DATABASE_SSL_ROOT_CERT:
            raise ValueError(
                "DATABASE_SSL_ROOT_CERT is required in production but not provided"
            )
        
        # Create certs directory if it doesn't exist (for Docker: /app/certs)
        cert_dir = Path("/app/certs") if os.path.exists("/app/certs") else Path(tempfile.gettempdir()) / "hit8_certs"
        cert_dir.mkdir(parents=True, exist_ok=True)
        
        # Write certificate content to file
        cert_file = cert_dir / "prod-ca-2021.crt"
        cert_file.write_text(settings.DATABASE_SSL_ROOT_CERT, encoding="utf-8")
        
        # Set restrictive permissions (read-only for owner)
        os.chmod(cert_file, 0o600)
        
        _ssl_cert_file_path = str(cert_file)
        logger.info(
            "ssl_cert_file_written",
            cert_file=_ssl_cert_file_path,
            environment=constants.ENVIRONMENT,
        )
        
        return _ssl_cert_file_path


def _get_db_connection():
    """
    Get database connection with SSL support for production Supabase.
    
    - Dev: No SSL (plain connection)
    - Production: SSL with certificate verification (required)
    
    Returns:
        psycopg.Connection: Database connection
    """
    conninfo = settings.DATABASE_CONNECTION_STRING
    
    # Production requires SSL with certificate verification
    if constants.ENVIRONMENT == "prd":
        if not settings.DATABASE_SSL_ROOT_CERT:
            raise ValueError(
                "DATABASE_SSL_ROOT_CERT is required in production but not provided"
            )
        
        # Write certificate content to file and get path
        cert_file_path = _get_ssl_cert_file_path()
        
        # Connect with SSL verification
        return psycopg.connect(
            conninfo,
            sslmode="verify-full",
            sslrootcert=cert_file_path,
        )
    
    # Dev: No SSL (local database)
    return psycopg.connect(conninfo)


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
        # Get query embedding
        embedding_model = _get_embedding_model()
        query_embedding = embedding_model.embed_query(query)
        
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


def create_tool_node(tool_name: str, tool_func: Callable[..., Any]):
    """Factory to create individual tool nodes."""
    def tool_node(state: "AgentState") -> "AgentState":
        """Execute a specific tool and return ToolMessage."""
        last_message = state["messages"][-1]
        
        # Find and execute tool calls for this specific tool
        tool_messages = []
        for tool_call in last_message.tool_calls:
            if tool_call.get("name") == tool_name:
                tool_call_id = tool_call.get("id", "")
                try:
                    logger.info(
                        f"tool_{tool_name}_executing",
                        tool_call_id=tool_call_id,
                        args=tool_call.get("args", {}),
                    )
                    
                    # Execute the tool with the provided arguments
                    result = tool_func(**tool_call.get("args", {}))
                    
                    # Create ToolMessage
                    tool_messages.append(
                        ToolMessage(
                            content=str(result),
                            tool_call_id=tool_call_id
                        )
                    )
                    
                    logger.info(
                        f"tool_{tool_name}_success",
                        tool_call_id=tool_call_id,
                        result_length=len(str(result)),
                    )
                except Exception as e:
                    logger.error(
                        f"tool_{tool_name}_error",
                        error=str(e),
                        error_type=type(e).__name__,
                        tool_call_id=tool_call_id,
                    )
                    tool_messages.append(
                        ToolMessage(
                            content=f"Error: {str(e)}",
                            tool_call_id=tool_call_id
                        )
                    )
        
        return {"messages": state["messages"] + tool_messages}
    
    return tool_node
