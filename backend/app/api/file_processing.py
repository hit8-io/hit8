"""
File processing utilities for document uploads.
"""
from __future__ import annotations

import structlog
from fastapi import UploadFile, HTTPException, status
from pathlib import Path

from app.api.document_utils import convert_to_markdown
from app.api.storage import upload_to_gcs

logger = structlog.get_logger(__name__)

# Allowed file extensions
ALLOWED_EXTENSIONS = {'.docx', '.xlsx', '.pptx', '.pdf', '.html', '.txt', '.csv', '.json', '.xml', '.epub'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


def validate_file(file: UploadFile) -> None:
    """Validate file type and size.
    
    Args:
        file: FastAPI UploadFile object
        
    Raises:
        HTTPException: If file is invalid
    """
    # Check file extension
    file_ext = Path(file.filename or '').suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type '{file_ext}' not supported. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    # Note: File size validation happens when reading the file
    # FastAPI UploadFile doesn't expose size before reading


async def process_uploaded_files(files: list[UploadFile], session_id: str) -> str:
    """Process uploaded files: validate, convert to markdown, and upload to GCS.
    
    Args:
        files: List of uploaded files
        session_id: Session/thread ID for GCS path
        
    Returns:
        Formatted string with converted markdown content from all files
        
    Raises:
        HTTPException: If file validation fails
    """
    if not files:
        return ""
    
    document_contents = []
    successful_files = []
    failed_files = []
    
    for file in files:
        try:
            # Validate file
            validate_file(file)
            
            # Read file content
            file_content = await file.read()
            
            # Check file size
            if len(file_content) > MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"File '{file.filename}' exceeds maximum size of {MAX_FILE_SIZE / (1024 * 1024):.0f}MB"
                )
            
            # Convert to markdown using file content
            markdown_content = convert_to_markdown(file_content, file.filename)
            
            # Upload original file to GCS
            gcs_path = upload_to_gcs(file_content, file.filename or 'unknown', session_id)
            
            # Format document content
            document_contents.append(f"## {file.filename}\n\n{markdown_content}")
            successful_files.append(file.filename)
            
            logger.debug(
                "file_processed_successfully",
                file_name=file.filename,
                session_id=session_id,
                gcs_path=gcs_path,
                markdown_length=len(markdown_content),
            )
            
        except HTTPException as e:
            # Log validation errors and continue with other files
            logger.warning(
                "file_validation_failed",
                file_name=file.filename,
                session_id=session_id,
                error=e.detail,
            )
            failed_files.append(file.filename)
            continue
        except Exception as e:
            # Log error and continue with other files
            logger.error(
                "file_processing_failed",
                file_name=file.filename,
                session_id=session_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            failed_files.append(file.filename)
            continue
    
    # If all files failed, raise error
    if not successful_files and failed_files:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process all files: {', '.join(failed_files)}"
        )
    
    # Log warnings for failed files
    if failed_files:
        logger.warning(
            "some_files_failed",
            failed_files=failed_files,
            successful_files=successful_files,
            session_id=session_id,
        )
    
    # Return formatted content
    if document_contents:
        return "\n\n---\n\n".join(document_contents)
    
    return ""
