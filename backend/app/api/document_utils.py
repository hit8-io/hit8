"""
Document conversion utilities using MarkItDown.
"""
from __future__ import annotations

import io
import structlog

from markitdown import MarkItDown

logger = structlog.get_logger(__name__)

# Initialize MarkItDown instance
md = MarkItDown()


def convert_to_markdown(file_content: bytes, file_name: str | None = None) -> str:
    """Convert file content to markdown using MarkItDown.
    
    Args:
        file_content: File content as bytes
        file_name: Optional filename for MarkItDown
        
    Returns:
        Markdown string content
        
    Raises:
        Exception: If conversion fails
    """
    try:
        # MarkItDown expects BinaryIO (file-like object), not raw bytes
        # Wrap bytes in BytesIO to create a file-like object
        file_like = io.BytesIO(file_content)
        result = md.convert(file_like, file_name=file_name)
        return result.text_content  # Returns markdown string
    except Exception as e:
        logger.error(
            "document_conversion_failed",
            file_name=file_name,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise
