"""
Tool for generating XLSX files from JSON content.
"""
from __future__ import annotations

import io
import json
import uuid

import pandas as pd
import structlog
from langchain_core.tools import tool

from app.api.storage import generate_signed_url, upload_output_to_gcs

logger = structlog.get_logger(__name__)

# XLSX MIME type
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@tool
def generate_xlsx(fileName: str, data: str, thread_id: str | None = None) -> str:
    """
    Generate an Excel spreadsheet (.xlsx) from JSON content and upload it to cloud storage.
    Returns a direct download URL that the user can click to download the file.
    
    Args:
        fileName: Name of the file to create (without .xlsx extension)
        data: JSON content to convert to Excel spreadsheet
        thread_id: Optional thread/session ID for organizing files. If not provided, a UUID will be generated.
        
    Returns:
        Direct download URL for the generated .xlsx file. The URL is valid for 60 minutes.
        
    Raises:
        ValueError: If fileName or data is empty, or if JSON is invalid
        Exception: If GCS upload or URL generation fails
    """
    # Validate inputs
    if not fileName or not fileName.strip():
        error_msg = "fileName cannot be empty"
        logger.error(
            "generate_xlsx_validation_failed",
            error=error_msg,
        )
        raise ValueError(error_msg)
    
    if not data or not data.strip():
        error_msg = "data cannot be empty"
        logger.error(
            "generate_xlsx_validation_failed",
            file_name=fileName,
            error=error_msg,
        )
        raise ValueError(error_msg)
    
    # Use provided thread_id or generate a fallback UUID
    if not thread_id:
        thread_id = str(uuid.uuid4())
        logger.warning(
            "generate_xlsx_no_thread_id",
            file_name=fileName,
            fallback_thread_id=thread_id,
        )
    
    # Ensure fileName has .xlsx extension
    if not fileName.endswith('.xlsx'):
        fileName = f"{fileName}.xlsx"
    
    try:
        logger.info(
            "generate_xlsx_started",
            file_name=fileName,
            thread_id=thread_id,
            json_length=len(data),
        )
        
        # Parse JSON data
        try:
            json_data = json.loads(data)
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON format: {str(e)}"
            logger.error(
                "generate_xlsx_json_parse_error",
                file_name=fileName,
                thread_id=thread_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise ValueError(error_msg) from e
        
        # Convert JSON to DataFrame based on structure
        if isinstance(json_data, list):
            if json_data and isinstance(json_data[0], dict):
                # List of dictionaries - convert directly to DataFrame
                df = pd.DataFrame(json_data)
            else:
                # Simple list of values - create DataFrame with single column
                df = pd.DataFrame(json_data, columns=["value"])
        elif isinstance(json_data, dict):
            # Dictionary - convert to DataFrame with keys as columns
            df = pd.DataFrame([json_data])
        else:
            # Single value - wrap in DataFrame
            df = pd.DataFrame([{"value": json_data}])
        
        # Write DataFrame to XLSX in memory
        xlsx_bytes = io.BytesIO()
        with pd.ExcelWriter(xlsx_bytes, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Sheet1')
        xlsx_bytes.seek(0)
        xlsx_content = xlsx_bytes.read()
        
        logger.debug(
            "generate_xlsx_conversion_complete",
            file_name=fileName,
            thread_id=thread_id,
            xlsx_size=len(xlsx_content),
            rows=len(df),
            columns=len(df.columns),
        )
        
        # Upload to GCS
        gcs_path = upload_output_to_gcs(
            file_content=xlsx_content,
            file_name=fileName,
            session_id=thread_id,
            content_type=XLSX_CONTENT_TYPE,
        )
        
        # Generate signed URL (valid for 60 minutes)
        signed_url = generate_signed_url(gcs_path, expiration_minutes=60)
        
        logger.info(
            "generate_xlsx_success",
            file_name=fileName,
            thread_id=thread_id,
            gcs_path=gcs_path,
            url_length=len(signed_url),
        )
        
        # Return only the URL
        return signed_url
        
    except ValueError as e:
        # Re-raise ValueError (validation or JSON parsing errors)
        raise
    except Exception as e:
        # GCS upload or other errors
        error_msg = f"Failed to generate and upload XLSX: {str(e)}"
        logger.exception(
            "generate_xlsx_failed",
            file_name=fileName,
            thread_id=thread_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise Exception(error_msg) from e
