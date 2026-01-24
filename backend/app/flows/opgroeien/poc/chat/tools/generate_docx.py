"""
Tool for generating DOCX files from markdown content.
"""
from __future__ import annotations

import os
import tempfile
import uuid

import pypandoc
import structlog
from langchain_core.tools import tool

from app.api.storage import generate_signed_url, upload_output_to_gcs

logger = structlog.get_logger(__name__)

# DOCX MIME type
DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@tool
def generate_docx(fileName: str, data: str, thread_id: str | None = None) -> str:
    """
    Generate a Word document (.docx) from markdown content and upload it to cloud storage.
    Returns a direct download URL that the user can click to download the file.
    
    Args:
        fileName: Name of the file to create (without .docx extension)
        data: Markdown content to convert to Word document
        thread_id: Optional thread/session ID for organizing files. If not provided, a UUID will be generated.
        
    Returns:
        Direct download URL for the generated .docx file. The URL is valid for 60 minutes.
        
    Raises:
        ValueError: If fileName or data is empty
        RuntimeError: If pandoc is not available or conversion fails
        Exception: If GCS upload or URL generation fails
    """
    # Validate inputs
    if not fileName or not fileName.strip():
        error_msg = "fileName cannot be empty"
        logger.error(
            "generate_docx_validation_failed",
            error=error_msg,
        )
        raise ValueError(error_msg)
    
    if not data or not data.strip():
        error_msg = "data cannot be empty"
        logger.error(
            "generate_docx_validation_failed",
            file_name=fileName,
            error=error_msg,
        )
        raise ValueError(error_msg)
    
    # Use provided thread_id or generate a fallback UUID
    if not thread_id:
        thread_id = str(uuid.uuid4())
        logger.warning(
            "generate_docx_no_thread_id",
            file_name=fileName,
            fallback_thread_id=thread_id,
        )
    
    # Ensure fileName has .docx extension
    if not fileName.endswith('.docx'):
        fileName = f"{fileName}.docx"
    
    try:
        logger.info(
            "generate_docx_started",
            file_name=fileName,
            thread_id=thread_id,
            markdown_length=len(data),
        )
        
        # Convert markdown to DOCX using pypandoc
        # Use temporary file approach since pypandoc.convert_text doesn't directly return bytes
        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as tmp_file:
            try:
                pypandoc.convert_text(
                    data,
                    'docx',
                    format='markdown-yaml_metadata_block',
                    outputfile=tmp_file.name,
                    extra_args=['--standalone'],
                )
                
                # Read the generated DOCX file
                with open(tmp_file.name, 'rb') as f:
                    docx_bytes = f.read()
                
                logger.debug(
                    "generate_docx_conversion_complete",
                    file_name=fileName,
                    thread_id=thread_id,
                    docx_size=len(docx_bytes),
                )
            finally:
                # Clean up temporary file
                try:
                    os.unlink(tmp_file.name)
                except OSError:
                    pass
        
        # Upload to GCS
        gcs_path = upload_output_to_gcs(
            file_content=docx_bytes,
            file_name=fileName,
            session_id=thread_id,
            content_type=DOCX_CONTENT_TYPE,
        )
        
        # Generate signed URL (valid for 60 minutes)
        signed_url = generate_signed_url(gcs_path, expiration_minutes=60)
        
        logger.info(
            "generate_docx_success",
            file_name=fileName,
            thread_id=thread_id,
            gcs_path=gcs_path,
            url_length=len(signed_url),
        )
        
        # Return only the URL
        return signed_url
        
    except RuntimeError as e:
        # pypandoc raises RuntimeError if pandoc is not installed
        error_msg = f"Pandoc is not available: {str(e)}"
        logger.error(
            "generate_docx_pandoc_error",
            file_name=fileName,
            thread_id=thread_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise RuntimeError(error_msg) from e
    except OSError as e:
        # File system errors
        error_msg = f"File system error during conversion: {str(e)}"
        logger.error(
            "generate_docx_filesystem_error",
            file_name=fileName,
            thread_id=thread_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise OSError(error_msg) from e
    except Exception as e:
        # GCS upload or other errors
        error_msg = f"Failed to generate and upload DOCX: {str(e)}"
        logger.exception(
            "generate_docx_failed",
            file_name=fileName,
            thread_id=thread_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise Exception(error_msg) from e
