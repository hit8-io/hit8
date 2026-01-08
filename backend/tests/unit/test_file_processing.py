"""
Unit tests for file processing utilities.
"""
from __future__ import annotations

import pytest
from fastapi import UploadFile, HTTPException
from io import BytesIO
from unittest.mock import patch, MagicMock, AsyncMock

from app.api.file_processing import validate_file, process_uploaded_files, ALLOWED_EXTENSIONS, MAX_FILE_SIZE


def test_validate_file_success():
    """Test successful file validation."""
    file = UploadFile(
        filename="test.docx",
        file=BytesIO(b"test content")
    )
    # Should not raise
    validate_file(file)


def test_validate_file_invalid_extension():
    """Test file validation with invalid extension."""
    file = UploadFile(
        filename="test.exe",
        file=BytesIO(b"test content")
    )
    
    with pytest.raises(HTTPException) as exc_info:
        validate_file(file)
    
    assert exc_info.value.status_code == 400
    assert "not supported" in exc_info.value.detail.lower()


def test_validate_file_no_extension():
    """Test file validation with no extension."""
    file = UploadFile(
        filename="test",
        file=BytesIO(b"test content")
    )
    
    with pytest.raises(HTTPException) as exc_info:
        validate_file(file)
    
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_process_uploaded_files_empty_list():
    """Test processing empty file list."""
    result = await process_uploaded_files([], "session123")
    assert result == ""


@pytest.mark.asyncio
async def test_process_uploaded_files_success():
    """Test successful file processing."""
    file = UploadFile(
        filename="test.docx",
        file=BytesIO(b"test content")
    )
    
    with patch("app.api.file_processing.convert_to_markdown") as mock_convert, \
         patch("app.api.file_processing.upload_to_gcs") as mock_upload:
        
        mock_convert.return_value = "# Test\n\nContent"
        mock_upload.return_value = "input/session123/test.docx"
        
        result = await process_uploaded_files([file], "session123")
        
        assert "## test.docx" in result
        assert "# Test" in result
        mock_convert.assert_called_once()
        mock_upload.assert_called_once()


@pytest.mark.asyncio
async def test_process_uploaded_files_size_exceeded():
    """Test file processing with file size exceeded."""
    large_content = b"x" * (MAX_FILE_SIZE + 1)
    file = UploadFile(
        filename="test.docx",
        file=BytesIO(large_content)
    )
    
    with pytest.raises(HTTPException) as exc_info:
        await process_uploaded_files([file], "session123")
    
    # When all files fail, we raise 500 with summary message
    assert exc_info.value.status_code == 500
    assert "failed to process all files" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_process_uploaded_files_invalid_type():
    """Test file processing with invalid file type."""
    file = UploadFile(
        filename="test.exe",
        file=BytesIO(b"test content")
    )
    
    with pytest.raises(HTTPException) as exc_info:
        await process_uploaded_files([file], "session123")
    
    # When all files fail, we raise 500 with summary message
    assert exc_info.value.status_code == 500
    assert "failed to process all files" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_process_uploaded_files_partial_failure():
    """Test file processing where some files fail."""
    valid_file = UploadFile(
        filename="test.docx",
        file=BytesIO(b"test content")
    )
    invalid_file = UploadFile(
        filename="test.exe",
        file=BytesIO(b"test content")
    )
    
    with patch("app.api.file_processing.convert_to_markdown") as mock_convert, \
         patch("app.api.file_processing.upload_to_gcs") as mock_upload:
        
        mock_convert.return_value = "# Test\n\nContent"
        mock_upload.return_value = "input/session123/test.docx"
        
        # Should process valid file and skip invalid one
        result = await process_uploaded_files([valid_file, invalid_file], "session123")
        
        # Should have content from valid file
        assert "## test.docx" in result
        # Should only process valid file
        assert mock_convert.call_count == 1
        assert mock_upload.call_count == 1
