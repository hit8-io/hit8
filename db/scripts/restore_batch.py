#!/usr/bin/env python3
"""
Restore a batch from GCS back into the database (Optimized).

Optimizations:
1. Streaming Restore: Downloads GCS files line-by-line and streams directly to DB.
2. COPY Protocol: Uses Postgres COPY for bulk insertion (50x faster than INSERT).
3. ID Preservation: Preserves original UUIDs to maintain external referential integrity.
4. O(1) Memory: Uses iterators instead of loading lists into RAM.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import tempfile
import uuid
import io
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

# Add backend to path
backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

# Add scripts directory to path for common module
scripts_path = Path(__file__).parent
sys.path.insert(0, str(scripts_path))

import structlog
import psycopg
from psycopg import sql
from psycopg.types.json import Json

from app.config import settings
from app import constants
from app.logging import configure_structlog, setup_logging
from app.api.knowledge_storage import get_knowledge_bucket_name
from app.api.storage import get_gcs_client
from common import get_db_connection

configure_structlog()
setup_logging()
logger = structlog.get_logger(__name__)

def stream_gcs_ndjson(bucket_name: str, blob_path: str) -> Iterator[dict]:
    """Generator that streams and yields parsed JSON objects from a GCS blob (handles gzip)."""
    client = get_gcs_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    
    if not blob.exists():
        logger.warning(f"blob_not_found_{blob_path}")
        return

    # Download to temp file to keep memory low
    with tempfile.TemporaryFile(mode='wb+') as tmp:
        blob.download_to_file(tmp)
        tmp.seek(0)
        
        # Handle gzip compression (if blob_path ends with .gz)
        if blob_path.endswith('.gz'):
            with gzip.open(tmp, 'rt', encoding='utf-8') as gz_file:
                for line in gz_file:
                    if line.strip():
                        yield json.loads(line)
        else:
            # Plain text JSONL
            tmp.seek(0)
            for line in tmp:
                if line.strip():
                    yield json.loads(line.decode('utf-8'))

def bulk_copy_from_iterator(cursor, table: str, columns: list[str], iterator: Iterator[dict], map_fn) -> int:
    """
    Uses Postgres COPY protocol to stream data into the database.
    map_fn converts a dict row to a tuple matching 'columns'.
    """
    count = 0
    with cursor.copy(f"COPY {table} ({', '.join(columns)}) FROM STDIN") as copy:
        for item in iterator:
            row = map_fn(item)
            copy.write_row(row)
            count += 1
    return count

def restore_batch(batch_id: str) -> dict[str, Any]:
    stats = {"batch_id": batch_id, "restored": False, "docs": 0, "chunks": 0}
    bucket_name = get_knowledge_bucket_name(constants.ENVIRONMENT)
    
    # 1. Check Metadata
    client = get_gcs_client()
    bucket = client.bucket(bucket_name)
    meta_blob = bucket.blob(f"{batch_id}/metadata.json")
    
    if not meta_blob.exists():
        raise ValueError(f"Batch {batch_id} not found in GCS")
        
    meta = json.loads(meta_blob.download_as_string())
    
    with get_db_connection(autocommit=False) as conn:
        with conn.cursor() as cur:
            # Check existing state
            cur.execute("SELECT status FROM hit8.batches WHERE id = %s", (batch_id,))
            res = cur.fetchone()
            if res and res[0] == 'active':
                raise ValueError("Batch is already active")
                
            logger.info("restore_started", batch_id=batch_id)
            
            # Upsert Batch Row
            # Handle metadata: psycopg will handle dict -> jsonb conversion automatically
            metadata_value = meta.get("metadata")
            if metadata_value is not None and isinstance(metadata_value, dict):
                # Use Json() wrapper for proper jsonb handling
                metadata_value = Json(metadata_value)
            
            # Handle created_at: use ISO string from archive, or current time if missing
            created_at_value = meta.get("created_at") or datetime.now().isoformat()
            
            cur.execute("""
                INSERT INTO hit8.batches (id, org, project, name, type, version, status, metadata, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, 'loading', %s, %s::timestamptz)
                ON CONFLICT (id) DO UPDATE SET status = 'loading'
            """, (
                meta["id"], meta["org"], meta["project"], meta["name"], 
                meta["type"], meta["version"], metadata_value, 
                created_at_value
            ))
            
            # Cleanup old data (idempotency)
            cur.execute("DELETE FROM hit8.documents WHERE batch_id = %s", (batch_id,))
            
            # 2. Restore Documents via COPY
            logger.info("restoring_documents")
            docs_iter = stream_gcs_ndjson(bucket_name, f"{batch_id}/artifacts/data-part-001.jsonl.gz")
            
            stats["docs"] = bulk_copy_from_iterator(
                cur, 
                "hit8.documents",
                ["id", "batch_id", "doc_key", "type", "content", "metadata", "created_at"],
                docs_iter,
                lambda d: (
                    d["id"], batch_id, d["doc_key"], d["type"], 
                    d["content"], json.dumps(d["metadata"]), d["created_at"]
                )
            )

            # 3. Restore Chunks/Embeddings
            # NOTE: We assume chunks/embeddings are in chunks.jsonl
            # We split them into two COPY operations (Chunks first, then Embeddings)
            # This requires reading the file twice OR buffering. 
            # To be efficient, we read chunks.jsonl once, write chunks to DB, 
            # and write embeddings to a temp buffer for the second pass.
            
            logger.info("restoring_chunks_embeddings")
            chunks_iter = stream_gcs_ndjson(bucket_name, f"{batch_id}/artifacts/data-part-002.jsonl.gz")
            
            emb_buffer = tempfile.TemporaryFile(mode='w+')
            
            def chunk_mapper(d):
                # Side-effect: write embedding to buffer for later
                # Format: chunk_id | embedding_vector | type | batch_id
                if d.get("embedding"):
                    # We write tab-separated values for direct COPY FROM STDIN later
                    # Need to format vector array string properly for COPY text format
                    vec_str = str(d["embedding"]).replace(" ", "") # "[1.0,2.0]"
                    emb_buffer.write(f"{d['chunk_id']}\t{vec_str}\t{d.get('embedding_type')}\t{batch_id}\n")
                
                return (
                    d["chunk_id"], d["document_id"], d["chunk_index"], 
                    d["content"], json.dumps(d["metadata"])
                )

            stats["chunks"] = bulk_copy_from_iterator(
                cur,
                "hit8.chunks",
                ["id", "document_id", "chunk_index", "content", "metadata"],
                chunks_iter,
                chunk_mapper
            )
            
            # 4. Restore Embeddings (from buffer)
            emb_buffer.seek(0)
            logger.info("restoring_embeddings_vector")
            with cur.copy("COPY hit8.embeddings (chunk_id, embedding, type, batch_id) FROM STDIN") as copy:
                while True:
                    chunk = emb_buffer.read(8192)
                    if not chunk: break
                    copy.write(chunk)
            
            # Finalize
            cur.execute("UPDATE hit8.batches SET status = 'active' WHERE id = %s", (batch_id,))
            conn.commit()
            stats["restored"] = True
            
    return stats

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("batch_id")
    args = parser.parse_args()
    try:
        res = restore_batch(args.batch_id)
        print(json.dumps(res, indent=2))
        return 0
    except Exception as e:
        logger.error("fatal_error", error=str(e))
        return 1

if __name__ == "__main__":
    sys.exit(main())
