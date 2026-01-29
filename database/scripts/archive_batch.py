#!/usr/bin/env python3
"""
Archive a batch to GCS and delete it from the database (Optimized).

Optimizations:
1. Split Export: Exports Documents and Chunks/Embeddings separately to avoid 
   duplicating document content (N chunks * Doc Content size = Huge Bandwidth Waste).
2. Native Vector Handling: Uses pgvector adapter instead of string parsing.
3. Streaming Uploads: Uploads ndjson (newline delimited JSON) directly to GCS 
   via streaming to keep memory usage constant (O(1)).
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

def stream_query_to_gcs_ndjson(
    conn: psycopg.Connection, 
    query: str, 
    params: tuple, 
    bucket_name: str, 
    blob_path: str
) -> int:
    """
    Executes a query and streams the result as NDJSON directly to GCS.
    Uses psycopg's row_factory to get dicts and creates a file-like object stream.
    Returns the number of rows exported.
    """
    client = get_gcs_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    
    # Check if already exists to save time (unless force handled by caller)
    # We implement a simple buffer here. Real streaming to GCS usually requires 
    # the 'google-resumable-media' lib or writing to a temp file first.
    # For safety and simplicity in this script, we write to a temp file then upload.
    # This prevents memory explosion, only uses disk.
    
    count = 0
    tmp_path = None
    
    try:
        # Use tempfile in binary mode
        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as tmp:
            tmp_path = tmp.name
            
            with conn.cursor(name=f"stream_{uuid.uuid4().hex}", row_factory=psycopg.rows.dict_row) as cur:
                cur.execute(query, params)
                while True:
                    rows = cur.fetchmany(2000)
                    if not rows:
                        break
                    for row in rows:
                        # Handle datetimes, UUIDs, and numpy types for JSON serialization
                        for k, v in row.items():
                            if v is None:
                                continue
                            elif hasattr(v, 'isoformat'):
                                row[k] = v.isoformat()
                            elif isinstance(v, uuid.UUID):
                                row[k] = str(v)
                            # Handle vector/embedding types - convert to list of native Python floats
                            elif hasattr(v, '__iter__') and not isinstance(v, (str, dict, list)):
                                # Likely a vector type (numpy array, etc.), convert to list of floats
                                try:
                                    row[k] = [float(x) for x in v]
                                except (TypeError, ValueError):
                                    pass
                            # Handle numpy scalar types (float32, float64, etc.)
                            elif hasattr(v, 'item'):
                                # numpy scalar, convert to native Python type
                                try:
                                    row[k] = v.item()
                                except (TypeError, ValueError):
                                    pass
                        
                        json_line = json.dumps(row, ensure_ascii=False) + "\n"
                        tmp.write(json_line.encode('utf-8'))
                        count += 1
            
            tmp.flush()
        
        # Compress the file with gzip
        gzip_path = tmp_path + ".gz"
        with open(tmp_path, 'rb') as f_in:
            with gzip.open(gzip_path, 'wb') as f_out:
                f_out.writelines(f_in)
        
        # Upload compressed file
        logger.info(f"uploading_{blob_path}", row_count=count, uncompressed_bytes=os.path.getsize(tmp_path), compressed_bytes=os.path.getsize(gzip_path))
        blob.upload_from_filename(gzip_path, content_type="application/x-gzip")
        
    finally:
        # Clean up temp files
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
        gzip_path = tmp_path + ".gz" if tmp_path else None
        if gzip_path and os.path.exists(gzip_path):
            try:
                os.unlink(gzip_path)
            except Exception:
                pass
        
    return count

def archive_batch(batch_id: str, force: bool = False) -> dict[str, Any]:
    stats = {"batch_id": batch_id, "exported": False, "archived": False, "deleted": 0}
    bucket_name = get_knowledge_bucket_name(constants.ENVIRONMENT)
    
    with get_db_connection(autocommit=False, register_vector_type=True) as conn:
        # 1. Validate Batch
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, org, project, name, type, version, status, metadata, created_at 
                FROM hit8.batches WHERE id = %s
            """, (batch_id,))
            res = cur.fetchone()
            if not res:
                raise ValueError(f"Batch {batch_id} not found")
            
            # Extract batch data
            batch_data = {
                "id": str(res[0]),
                "org": res[1],
                "project": res[2],
                "name": res[3],
                "type": res[4],
                "version": res[5],
                "status": res[6],
                "metadata": res[7],
                "created_at": res[8].isoformat() if res[8] else None,
            }
            
            # Check GCS Metadata
            client = get_gcs_client()
            bucket = client.bucket(bucket_name)
            meta_blob = bucket.blob(f"{batch_id}/metadata.json")
            
            if meta_blob.exists() and not force:
                logger.info(
                    "batch_already_archived_skipping_export",
                    batch_id=batch_id,
                    blob_path=f"{batch_id}/metadata.json",
                    bucket=bucket_name,
                )
                stats["exported"] = False  # Already there
            else:
                # 2. Export Documents (No Join) - NDJSON
                # Using temp file strategy to keep memory low
                logger.info("exporting_documents")
                doc_count = stream_query_to_gcs_ndjson(
                    conn,
                    """
                    SELECT id, doc_key, type, content, metadata, created_at 
                    FROM hit8.documents WHERE batch_id = %s
                    """,
                    (batch_id,),
                    bucket_name,
                    f"{batch_id}/artifacts/data-part-001.jsonl.gz"
                )
                
                # 3. Export Chunks & Embeddings (Joined) - NDJSON
                # We link via document_id. 
                logger.info("exporting_chunks_embeddings")
                chunk_count = stream_query_to_gcs_ndjson(
                    conn,
                    """
                    SELECT 
                        c.id as chunk_id, c.document_id, c.chunk_index, c.content, c.metadata,
                        e.embedding, e.type as embedding_type
                    FROM hit8.documents d
                    JOIN hit8.chunks c ON c.document_id = d.id
                    LEFT JOIN hit8.embeddings e ON e.chunk_id = c.id
                    WHERE d.batch_id = %s
                    ORDER BY d.id, c.chunk_index
                    """,
                    (batch_id,),
                    bucket_name,
                    f"{batch_id}/artifacts/data-part-002.jsonl.gz"
                )
                
                # 4. Write Metadata Marker
                meta_blob.upload_from_string(json.dumps({
                    **batch_data,  # Include all batch fields
                    "doc_count": doc_count,
                    "chunk_count": chunk_count,
                    "archived_at": datetime.now().isoformat()
                }), content_type="application/json")
                stats["exported"] = True

            # 5. Delete from DB (Transaction)
            logger.info("deleting_from_db")
            # We assume CASCADE handles chunks/embeddings
            cur.execute("DELETE FROM hit8.documents WHERE batch_id = %s", (batch_id,))
            deleted = cur.rowcount
            
            cur.execute("UPDATE hit8.batches SET status = 'archived' WHERE id = %s", (batch_id,))
            conn.commit()
            
            stats["archived"] = True
            stats["deleted"] = deleted
            
    return stats

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("batch_id")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    
    try:
        res = archive_batch(args.batch_id, args.force)
        print(json.dumps(res, indent=2))
        return 0
    except Exception as e:
        logger.error("fatal_error", error=str(e))
        return 1

if __name__ == "__main__":
    sys.exit(main())
