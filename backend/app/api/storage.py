"""
GCS storage utilities for document uploads.
"""
from __future__ import annotations

import json
from datetime import timedelta

import structlog
from google.cloud import storage
from google.oauth2 import service_account

from app import constants
from app.config import settings

logger = structlog.get_logger(__name__)

# OAuth scope for GCS
OAUTH_SCOPE_CLOUD_PLATFORM = "https://www.googleapis.com/auth/cloud-platform"

# Initialize GCS client
_client: storage.Client | None = None


def get_gcs_client() -> storage.Client:
    """Get or create GCS client instance with service account credentials."""
    global _client
    if _client is None:
        service_account_info = json.loads(settings.VERTEX_SERVICE_ACCOUNT)
        
        creds = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=[OAUTH_SCOPE_CLOUD_PLATFORM]
        )
        
        _client = storage.Client(credentials=creds)
        
        logger.debug("gcs_client_initialized")
    
    return _client


def get_chat_bucket_name() -> str:
    """Get bucket name based on environment.
    
    Returns:
        Bucket name: hit8-poc-{env}-chat
    """
    env = constants.ENVIRONMENT
    return f"hit8-poc-{env}-chat"


def upload_to_gcs(file_content: bytes, file_name: str, session_id: str) -> str:
    """Upload file to GCS at path input/<session_id>/<filename>.
    
    Args:
        file_content: File content as bytes
        file_name: Original filename
        session_id: Session/thread ID
        
    Returns:
        GCS path: input/<session_id>/<filename>
        
    Raises:
        Exception: If upload fails
    """
    try:
        bucket_name = get_chat_bucket_name()
        client = get_gcs_client()
        bucket = client.bucket(bucket_name)
        
        # Create GCS path: input/<session_id>/<filename>
        gcs_path = f"input/{session_id}/{file_name}"
        
        # Upload file
        blob = bucket.blob(gcs_path)
        blob.upload_from_string(file_content, content_type="application/octet-stream")
        
        logger.debug(
            "file_uploaded_to_gcs",
            bucket_name=bucket_name,
            gcs_path=gcs_path,
            file_name=file_name,
            session_id=session_id,
            file_size=len(file_content),
        )
        
        return gcs_path
    except Exception as e:
        logger.error(
            "gcs_upload_failed",
            file_name=file_name,
            session_id=session_id,
            bucket_name=get_chat_bucket_name(),
            error=str(e),
            error_type=type(e).__name__,
        )
        raise


def upload_output_to_gcs(
    file_content: bytes,
    file_name: str,
    session_id: str,
    content_type: str,
) -> str:
    """Upload generated output file to GCS at path output/<session_id>/<filename>.
    
    Args:
        file_content: File content as bytes
        file_name: Filename for the output file
        session_id: Session/thread ID
        content_type: MIME type of the file (e.g., application/vnd.openxmlformats-officedocument.wordprocessingml.document)
        
    Returns:
        GCS path: output/<session_id>/<filename>
        
    Raises:
        Exception: If upload fails
    """
    try:
        bucket_name = get_chat_bucket_name()
        client = get_gcs_client()
        bucket = client.bucket(bucket_name)
        
        # Create GCS path: output/<session_id>/<filename>
        gcs_path = f"output/{session_id}/{file_name}"
        
        # Upload file
        blob = bucket.blob(gcs_path)
        blob.upload_from_string(file_content, content_type=content_type)
        
        logger.debug(
            "output_file_uploaded_to_gcs",
            bucket_name=bucket_name,
            gcs_path=gcs_path,
            file_name=file_name,
            session_id=session_id,
            file_size=len(file_content),
            content_type=content_type,
        )
        
        return gcs_path
    except Exception as e:
        logger.error(
            "gcs_output_upload_failed",
            file_name=file_name,
            session_id=session_id,
            bucket_name=get_chat_bucket_name(),
            error=str(e),
            error_type=type(e).__name__,
        )
        raise


def generate_signed_url(gcs_path: str, expiration_minutes: int = 60) -> str:
    """Generate a time-limited signed URL for a GCS object.
    
    Args:
        gcs_path: GCS path to the object (e.g., output/<session_id>/<filename>)
        expiration_minutes: Number of minutes until the URL expires (default: 60)
        
    Returns:
        Signed URL string that can be used to download the file
        
    Raises:
        Exception: If URL generation fails
    """
    try:
        bucket_name = get_chat_bucket_name()
        client = get_gcs_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(gcs_path)
        
        url = blob.generate_signed_url(
            expiration=timedelta(minutes=expiration_minutes),
            method='GET',
        )
        
        logger.debug(
            "signed_url_generated",
            bucket_name=bucket_name,
            gcs_path=gcs_path,
            expiration_minutes=expiration_minutes,
        )
        
        return url
    except Exception as e:
        logger.error(
            "signed_url_generation_failed",
            gcs_path=gcs_path,
            bucket_name=get_chat_bucket_name(),
            error=str(e),
            error_type=type(e).__name__,
        )
        raise
