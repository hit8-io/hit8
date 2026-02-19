"""
Unit tests for document conversion utilities.
"""
from __future__ import annotations

import pytest
from io import BytesIO
from unittest.mock import patch, MagicMock

from app.api.file_processing import convert_to_markdown


@pytest.mark.asyncio
async def test_convert_to_markdown_success():
    """Test successful document conversion to markdown."""
    # Mock MarkItDown
    with patch("app.api.file_processing.md") as mock_md:
        mock_result = MagicMock()
        mock_result.text_content = "# Test Document\n\nThis is test content."
        mock_md.convert.return_value = mock_result
        
        # Test with bytes and filename
        file_content = b"fake file content"
        result = convert_to_markdown(file_content, "test.docx")
        
        assert result == "# Test Document\n\nThis is test content."
        # Note: convert is called with BytesIO object, not raw bytes
        assert mock_md.convert.called


@pytest.mark.asyncio
async def test_convert_to_markdown_failure():
    """Test document conversion failure handling."""
    with patch("app.api.file_processing.md") as mock_md:
        mock_md.convert.side_effect = Exception("Conversion failed")
        
        file_content = b"fake file content"
        
        with pytest.raises(Exception) as exc_info:
            convert_to_markdown(file_content, "test.docx")
        
        assert "Conversion failed" in str(exc_info.value)
