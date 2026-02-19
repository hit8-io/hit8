"""
GCS storage utilities for knowledge batch storage (RAG artifacts).
"""
from __future__ import annotations

import gzip
import json
from typing import Any

import structlog
from google.cloud import storage

from app import constants
from app.api.storage import get_gcs_client

logger = structlog.get_logger(__name__)


def get_knowledge_bucket_name(env: str | None = None) -> str:
    """Get knowledge bucket name based on environment.
    
    Args:
        env: Environment name (dev/stg/prd). If None, uses constants.ENVIRONMENT.
    
    Returns:
        Bucket name: hit8-poc-{env}-knowledge
    """
    if env is None:
        env = constants.ENVIRONMENT
    return f"hit8-poc-{env}-knowledge"


def upload_batch_metadata(batch_id: str, metadata: dict[str, Any], env: str | None = None) -> str:
    """Upload batch metadata.json to GCS.
    
    Directory structure: <batch_uuid>/metadata.json
    
    Args:
        batch_id: UUID of the batch
        metadata: Metadata dictionary (must include id, org, project, name, type, version, created_at, doc_count)
        env: Environment name (dev/stg/prd). If None, uses constants.ENVIRONMENT.
    
    Returns:
        GCS path: <batch_id>/metadata.json
        
    Raises:
        Exception: If upload fails
    """
    try:
        bucket_name = get_knowledge_bucket_name(env)
        client = get_gcs_client()
        bucket = client.bucket(bucket_name)
        
        # Create GCS path: <batch_id>/metadata.json
        gcs_path = f"{batch_id}/metadata.json"
        
        # Serialize metadata to JSON
        metadata_json = json.dumps(metadata, indent=2, ensure_ascii=False)
        
        # Upload file
        blob = bucket.blob(gcs_path)
        blob.upload_from_string(metadata_json, content_type="application/json")
        
        logger.info(
            "batch_metadata_uploaded",
            bucket_name=bucket_name,
            gcs_path=gcs_path,
            batch_id=batch_id,
        )
        
        return gcs_path
    except Exception as e:
        logger.error(
            "batch_metadata_upload_failed",
            batch_id=batch_id,
            bucket_name=get_knowledge_bucket_name(env),
            error=str(e),
            error_type=type(e).__name__,
        )
        raise


def upload_batch_artifacts(
    batch_id: str,
    artifacts: list[dict[str, Any]],
    part_number: int = 1,
    env: str | None = None,
) -> str:
    """Upload batch artifacts as compressed JSONL to GCS.
    
    Directory structure: <batch_uuid>/artifacts/data-part-{part_number:03d}.jsonl.gz
    
    Artifact format: {"doc_key": "...", "chunk": 0, "content": "...", "vector": [...], "metadata": {...}}
    
    Args:
        batch_id: UUID of the batch
        artifacts: List of artifact dictionaries (doc_key, chunk, content, vector, metadata)
        part_number: Part number for multi-part uploads (default: 1)
        env: Environment name (dev/stg/prd). If None, uses constants.ENVIRONMENT.
    
    Returns:
        GCS path: <batch_id>/artifacts/data-part-{part_number:03d}.jsonl.gz
        
    Raises:
        Exception: If upload fails
    """
    try:
        bucket_name = get_knowledge_bucket_name(env)
        client = get_gcs_client()
        bucket = client.bucket(bucket_name)
        
        # Create GCS path: <batch_id>/artifacts/data-part-{part_number:03d}.jsonl.gz
        artifact_filename = f"data-part-{part_number:03d}.jsonl.gz"
        gcs_path = f"{batch_id}/artifacts/{artifact_filename}"
        
        # Compress artifacts as JSONL
        jsonl_content = "\n".join(json.dumps(artifact, ensure_ascii=False) for artifact in artifacts)
        compressed_content = gzip.compress(jsonl_content.encode("utf-8"))
        
        # Upload file
        blob = bucket.blob(gcs_path)
        blob.upload_from_string(compressed_content, content_type="application/gzip")
        
        logger.info(
            "batch_artifacts_uploaded",
            bucket_name=bucket_name,
            gcs_path=gcs_path,
            batch_id=batch_id,
            part_number=part_number,
            artifact_count=len(artifacts),
            compressed_size=len(compressed_content),
        )
        
        return gcs_path
    except Exception as e:
        logger.error(
            "batch_artifacts_upload_failed",
            batch_id=batch_id,
            part_number=part_number,
            bucket_name=get_knowledge_bucket_name(env),
            error=str(e),
            error_type=type(e).__name__,
        )
        raise


def download_batch_metadata(batch_id: str, env: str | None = None) -> dict[str, Any]:
    """Download batch metadata.json from GCS.
    
    Args:
        batch_id: UUID of the batch
        env: Environment name (dev/stg/prd). If None, uses constants.ENVIRONMENT.
    
    Returns:
        Metadata dictionary
        
    Raises:
        Exception: If download fails or metadata not found
    """
    try:
        bucket_name = get_knowledge_bucket_name(env)
        client = get_gcs_client()
        bucket = client.bucket(bucket_name)
        
        # GCS path: <batch_id>/metadata.json
        gcs_path = f"{batch_id}/metadata.json"
        blob = bucket.blob(gcs_path)
        
        if not blob.exists():
            raise FileNotFoundError(f"Batch metadata not found: {gcs_path}")
        
        # Download and parse JSON
        metadata_json = blob.download_as_text()
        metadata = json.loads(metadata_json)
        
        logger.debug(
            "batch_metadata_downloaded",
            bucket_name=bucket_name,
            gcs_path=gcs_path,
            batch_id=batch_id,
        )
        
        return metadata
    except Exception as e:
        logger.error(
            "batch_metadata_download_failed",
            batch_id=batch_id,
            bucket_name=get_knowledge_bucket_name(env),
            error=str(e),
            error_type=type(e).__name__,
        )
        raise


def list_batches(prefix: str | None = None, env: str | None = None) -> list[str]:
    """List all batch IDs in the knowledge bucket.
    
    Args:
        prefix: Optional prefix filter (e.g., for org/project filtering)
        env: Environment name (dev/stg/prd). If None, uses constants.ENVIRONMENT.
    
    Returns:
        List of batch IDs (UUIDs)
    """
    try:
        bucket_name = get_knowledge_bucket_name(env)
        client = get_gcs_client()
        bucket = client.bucket(bucket_name)
        
        # List all blobs with metadata.json pattern
        # Pattern: <batch_id>/metadata.json
        blobs = bucket.list_blobs(prefix=prefix)
        
        batch_ids = set()
        for blob in blobs:
            # Extract batch_id from path: <batch_id>/metadata.json
            if blob.name.endswith("/metadata.json"):
                batch_id = blob.name.rsplit("/", 1)[0]
                batch_ids.add(batch_id)
        
        batch_ids_list = sorted(list(batch_ids))
        
        logger.debug(
            "batches_listed",
            bucket_name=bucket_name,
            prefix=prefix,
            batch_count=len(batch_ids_list),
        )
        
        return batch_ids_list
    except Exception as e:
        logger.error(
            "batches_list_failed",
            prefix=prefix,
            bucket_name=get_knowledge_bucket_name(env),
            error=str(e),
            error_type=type(e).__name__,
        )
        raise


def rebuild_batch_from_gcs(batch_id: str, env: str | None = None) -> None:
    """Rebuild batch from GCS artifacts (disaster recovery).
    
    This function reads metadata.json and artifacts/*.jsonl.gz files from GCS
    and reconstructs the batch in the database. This is a placeholder for
    future implementation.
    
    Args:
        batch_id: UUID of the batch
        env: Environment name (dev/stg/prd). If None, uses constants.ENVIRONMENT.
    
    Raises:
        NotImplementedError: This function is not yet implemented
    """
    # TODO: Implement batch rebuild from GCS
    # 1. Download metadata.json
    # 2. List and download all artifacts/*.jsonl.gz files
    # 3. Decompress and parse JSONL
    # 4. Insert into database (batches, documents, chunks, embeddings tables)
    raise NotImplementedError("rebuild_batch_from_gcs is not yet implemented")
