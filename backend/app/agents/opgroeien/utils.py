"""
Utility functions for the opgroeien agent - vector stores and embeddings.
"""
from __future__ import annotations

import json
import math
from typing import Any

import psycopg
from psycopg import sql as psql
import structlog
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.config import settings

logger = structlog.get_logger(__name__)

# Cache embedding model
_embedding_model: GoogleGenerativeAIEmbeddings | None = None


def _get_embedding_model() -> GoogleGenerativeAIEmbeddings:
    """Get or create cached embedding model."""
    global _embedding_model
    if _embedding_model is None:
        import json
        from google.oauth2 import service_account
        
        service_account_info = json.loads(settings.vertex_service_account_json)
        project_id = service_account_info["project_id"]
        
        creds = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=['https://www.googleapis.com/auth/cloud-platform']
        )
        
        _embedding_model = GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-001",
            task_type="retrieval_document",
            output_dimensionality=1536,  # Match database embedding dimensions
            model_kwargs={"provider": "vertexai"},
            project=project_id,
            location=settings.vertex_ai_location,
            credentials=creds,
        )
    return _embedding_model


def _vector_search_raw_sql(
    query: str,
    table_name: str,
    k: int = 40,
) -> list[tuple[dict[str, Any], float]]:
    """
    Perform vector similarity search using raw SQL queries on custom tables.
    
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
        Score is cosine distance (lower is more similar, converted to similarity: 1 - distance)
    """
    # Validate table name to prevent SQL injection
    allowed_tables = {"embeddings_proc", "embeddings_regel"}
    if table_name not in allowed_tables:
        raise ValueError(f"Invalid table name: {table_name}. Allowed: {allowed_tables}")
    
    try:
        # Get query embedding (already 1536 dimensions via output_dimensionality parameter)
        embedding_model = _get_embedding_model()
        query_embedding = embedding_model.embed_query(query)
        
        # Verify dimension matches expected 1536
        if len(query_embedding) != 1536:
            logger.warning(
                "embedding_dimension_mismatch",
                expected_dim=1536,
                actual_dim=len(query_embedding),
            )
        
        # Normalize the vector (L2 normalization)
        norm = math.sqrt(sum(x * x for x in query_embedding))
        if norm > 0:
            query_embedding = [x / norm for x in query_embedding]
        
        # Convert embedding list to PostgreSQL array format
        embedding_array = "[" + ",".join(str(x) for x in query_embedding) + "]"
        
        # Connect to database and execute query
        with psycopg.connect(settings.database_connection_string) as conn:
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
                
                results = []
                for row in cursor.fetchall():
                    content, metadata, doc, chunk, score = row
                    
                    # Parse metadata if it's a string
                    if isinstance(metadata, str):
                        try:
                            metadata = json.loads(metadata)
                        except json.JSONDecodeError:
                            metadata = {}
                    elif metadata is None:
                        metadata = {}
                    
                    result_dict = {
                        "content": content or "",
                        "metadata": metadata,
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

