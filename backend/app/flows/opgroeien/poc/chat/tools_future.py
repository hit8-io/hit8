"""
Future/unused tools for the opgroeien agent.

These tools are not currently active but are kept for future use.
To enable a tool, uncomment it here and add it to get_all_tools() in tools.py.
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any

import markdown
import requests
import structlog
from docx import Document
from langchain_core.tools import tool
from openpyxl import Workbook

from app.flows.opgroeien.poc.constants import (
    COLLECTION_PROCEDURES,
    COLLECTION_REGELGEVING,
    VECTOR_SEARCH_DOC_K,
)
from app.flows.opgroeien.poc.chat.tools_utils import (
    _vector_search_raw_sql,
)

logger = structlog.get_logger(__name__)


@tool
def fetch_webpage(URL: str) -> str:
    """
    Fetches an URL and returns the HTML content.
    
    Args:
        URL: The URL to fetch
        
    Returns:
        HTML content as string
    """
    try:
        response = requests.get(URL, timeout=10)
        response.raise_for_status()
        return response.text
    except Exception as e:
        logger.error(
            "fetch_webpage_failed",
            url=URL,
            error=str(e),
            error_type=type(e).__name__,
        )
        return f"Error fetching webpage: {str(e)}"


@tool
def generate_docx(fileName: str, data: str) -> str:
    """
    Convert a markdown file to .docx. It will return an URL to download the file.
    
    Args:
        fileName: Name of the file to create
        data: Markdown content to convert
        
    Returns:
        URL or path to the generated .docx file
    """
    try:
        # Convert markdown to HTML, then to docx
        html = markdown.markdown(data)
        
        # Create a temporary file
        temp_dir = Path(tempfile.gettempdir())
        file_path = temp_dir / f"{fileName}.docx"
        
        # Create docx document
        doc = Document()
        
        # Simple conversion: split by paragraphs and add to docx
        paragraphs = html.split('\n')
        for para in paragraphs:
            if para.strip():
                # Remove HTML tags for simple text
                clean_text = re.sub(r'<[^>]+>', '', para)
                if clean_text.strip():
                    doc.add_paragraph(clean_text.strip())
        
        doc.save(str(file_path))
        
        # Return file path (in production, this could be uploaded to storage and return URL)
        return str(file_path)
    except Exception as e:
        logger.error(
            "generate_docx_failed",
            file_name=fileName,
            error=str(e),
            error_type=type(e).__name__,
        )
        return f"Error generating docx: {str(e)}"


@tool
def generate_xlsx(fileName: str, data: str) -> str:
    """
    Convert a json file to .xlsx. It will return an URL to download the file.
    
    Args:
        fileName: Name of the file to create
        data: JSON content to convert
        
    Returns:
        URL or path to the generated .xlsx file
    """
    try:
        # Parse JSON data
        json_data = json.loads(data)
        
        # Create a temporary file
        temp_dir = Path(tempfile.gettempdir())
        file_path = temp_dir / f"{fileName}.xlsx"
        
        # Create workbook
        wb = Workbook()
        ws = wb.active
        
        # Handle different JSON structures
        if isinstance(json_data, list):
            if json_data and isinstance(json_data[0], dict):
                # List of dictionaries - use keys as headers
                headers = list(json_data[0].keys())
                ws.append(headers)
                for row in json_data:
                    ws.append([row.get(h, "") for h in headers])
            else:
                # Simple list
                for item in json_data:
                    ws.append([item])
        elif isinstance(json_data, dict):
            # Dictionary - convert to rows
            for key, value in json_data.items():
                ws.append([key, value])
        else:
            # Single value
            ws.append([json_data])
        
        wb.save(str(file_path))
        
        # Return file path (in production, this could be uploaded to storage and return URL)
        return str(file_path)
    except Exception as e:
        logger.error(
            "generate_xlsx_failed",
            file_name=fileName,
            error=str(e),
            error_type=type(e).__name__,
        )
        return f"Error generating xlsx: {str(e)}"


@tool
def extract_entities(chatInput: str) -> str:
    """
    Tool that extract key entities from a text, e.g. to further query a knowledge graph
    
    Args:
        chatInput: The text to extract entities from
        
    Returns:
        JSON string with extracted entities
    """
    try:
        # This is a placeholder - in production, this would use an LLM or NER model
        entities = {
            "entities": [],
            "text": chatInput,
            "note": "Entity extraction not fully implemented - placeholder response"
        }
        return json.dumps(entities, ensure_ascii=False)
    except Exception as e:
        logger.error(
            "extract_entities_failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        return json.dumps({"error": f"Failed to extract entities: {str(e)}"})


@tool
def query_knowledge_graph(entities: str) -> str:
    """
    Query an internal knowledge graph with as input a list of entities, returning a list of connected entities
    
    Args:
        entities: JSON string with list of entities
        
    Returns:
        JSON string with connected entities
    """
    try:
        # Parse entities
        entity_list = json.loads(entities) if isinstance(entities, str) else entities
        
        # This is a placeholder - in production, this would query an actual knowledge graph
        result = {
            "input_entities": entity_list,
            "connected_entities": [],
            "note": "Knowledge graph query not fully implemented - placeholder response"
        }
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        logger.error(
            "query_knowledge_graph_failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        return json.dumps({"error": f"Failed to query knowledge graph: {str(e)}"})


@tool
def get_procedure(doc: str) -> str:
    """
    Get the complete content of a procedure given its name as parameters. A name is e.g. "PR-AV-02".
    
    Return:
    - doc (equals name of the procedure)
    - content
    - metadata (json with all metadata)
    
    Args:
        doc: The procedure name (e.g., "PR-AV-02")
        
    Returns:
        JSON string with doc, content, and metadata
    """
    try:
        # Search for procedure by doc name
        results = _vector_search_raw_sql(f"procedure {doc}", COLLECTION_PROCEDURES, k=VECTOR_SEARCH_DOC_K)
        
        # Combine all chunks for this procedure
        content_parts = []
        metadata_dict = {}
        
        for result_dict, _ in results:
            content = result_dict.get("content", "")
            if content:
                content_parts.append(content)
            if result_dict.get("metadata"):
                metadata_dict.update(result_dict["metadata"])
        
        result = {
            "doc": doc,
            "content": "\n\n".join(content_parts),
            "metadata": metadata_dict
        }
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        logger.error(
            "get_procedure_failed",
            doc=doc,
            error=str(e),
            error_type=type(e).__name__,
        )
        return json.dumps({"error": f"Failed to get procedure: {str(e)}"})


@tool
def get_regelgeving(doc: str) -> str:
    """
    Get the complete content of regelgeving given its name.
    
    Args:
        doc: The regelgeving document name
        
    Returns:
        JSON string with doc, content, and metadata
    """
    try:
        # Search for regelgeving by doc name
        results = _vector_search_raw_sql(f"regelgeving {doc}", COLLECTION_REGELGEVING, k=VECTOR_SEARCH_DOC_K)
        
        # Combine all chunks for this document
        content_parts = []
        metadata_dict = {}
        
        for result_dict, _ in results:
            content = result_dict.get("content", "")
            if content:
                content_parts.append(content)
            if result_dict.get("metadata"):
                metadata_dict.update(result_dict["metadata"])
        
        result = {
            "doc": doc,
            "content": "\n\n".join(content_parts),
            "metadata": metadata_dict
        }
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        logger.error(
            "get_regelgeving_failed",
            doc=doc,
            error=str(e),
            error_type=type(e).__name__,
        )
        return json.dumps({"error": f"Failed to get regelgeving: {str(e)}"})

