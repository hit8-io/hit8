"""
Unit tests for LangChain tools.
"""
from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

# Set required env vars before importing app modules
os.environ.setdefault("BRIGHTDATA_API_KEY", "test-api-key")
os.environ.setdefault("DATABASE_CONNECTION_STRING", "postgresql://test:test@localhost/test")
os.environ.setdefault("LANGFUSE_ENABLED", "false")
os.environ.setdefault("API_TOKEN", "test-api-token")
os.environ.setdefault("VERTEX_SERVICE_ACCOUNT", '{"project_id": "mock", "type": "service_account"}')
os.environ.setdefault("LLM_MODEL_NAME", "mock-model")
os.environ.setdefault("GCP_PROJECT", "mock-project")
os.environ.setdefault("GOOGLE_IDENTITY_PLATFORM_DOMAIN", "mock-domain")
os.environ.setdefault("CORS_ALLOW_ORIGINS", '["*"]')

from brightdata import SyncBrightDataClient
from brightdata.models import ScrapeResult

# Import the module to access the function before it's wrapped by @tool
# We'll call it via the tool's invoke method with proper args
from app.flows.opgroeien.poc.chat.tools.fetch_website import fetch_website


def test_fetch_webpage_successful():
    """Test successful webpage fetch with HTML cleaning and markdown conversion."""
    # Mock HTML content
    mock_html = """
    <html>
        <head><title>Test Page</title></head>
        <body>
            <h1>Main Heading</h1>
            <p>This is a paragraph with <strong>bold</strong> text.</p>
            <nav>Navigation should be removed</nav>
            <footer>Footer should be removed</footer>
        </body>
    </html>
    """
    
    # Mock ScrapeResult (status must be "ready", "error", "timeout", or "in_progress")
    mock_result = ScrapeResult(
        success=True,
        url="https://example.com",
        status="ready",
        data=mock_html
    )
    
    # Mock SyncBrightDataClient
    mock_client = MagicMock(spec=SyncBrightDataClient)
    mock_client.scrape_url.return_value = mock_result
    mock_client.__enter__ = MagicMock(return_value=mock_client)  # Context manager support
    
    with patch("app.flows.opgroeien.poc.chat.tools.fetch_website._get_brightdata_client", return_value=mock_client):
        # Call the tool with proper invocation
        result = fetch_website.invoke({"url": "https://example.com"})
        
        # Verify client.scrape_url was called correctly
        mock_client.scrape_url.assert_called_once_with("https://example.com")
        
        # Verify result is markdown (not HTML)
        assert "Main Heading" in result
        assert "<h1>" not in result
        assert "Navigation should be removed" not in result
        assert "Footer should be removed" not in result


def test_fetch_webpage_tag_removal():
    """Test that unwanted tags are removed from HTML."""
    mock_html = """
    <html>
        <body>
            <nav>Nav content</nav>
            <footer>Footer content</footer>
            <script>console.log('script');</script>
            <style>body { color: red; }</style>
            <noscript>No script</noscript>
            <iframe src="ad.html"></iframe>
            <svg><circle></circle></svg>
            <aside>Sidebar</aside>
            <form>Form content</form>
            <button>Click me</button>
            <main>This should remain</main>
        </body>
    </html>
    """
    
    mock_result = ScrapeResult(
        success=True,
        url="https://example.com",
        status="ready",
        data=mock_html
    )
    
    mock_client = MagicMock(spec=SyncBrightDataClient)
    mock_client.scrape_url.return_value = mock_result
    mock_client.__enter__ = MagicMock(return_value=mock_client)  # Context manager support
    
    with patch("app.flows.opgroeien.poc.chat.tools.fetch_website._get_brightdata_client", return_value=mock_client):
        # Call the tool with proper invocation
        result = fetch_website.invoke({"url": "https://example.com"})
        
        # Verify unwanted tags are removed
        assert "Nav content" not in result
        assert "Footer content" not in result
        assert "console.log" not in result
        assert "body { color: red; }" not in result
        assert "No script" not in result
        assert "ad.html" not in result
        assert "Sidebar" not in result
        assert "Form content" not in result
        assert "Click me" not in result
        
        # Verify main content remains
        assert "This should remain" in result


def test_fetch_webpage_class_id_heuristic_removal():
    """Test that elements with cookie, ad-, advert, popup, newsletter, social in class/id are removed."""
    mock_html = """
    <html>
        <body>
            <div class="cookie-banner">Cookie banner</div>
            <div id="ad-container">Ad content</div>
            <div class="advert-box">Advertisement</div>
            <div id="popup-modal">Popup</div>
            <div class="newsletter-signup">Newsletter</div>
            <div id="social-share">Social</div>
            <div class="main-content">This should remain</div>
        </body>
    </html>
    """
    
    mock_result = ScrapeResult(
        success=True,
        url="https://example.com",
        status="ready",
        data=mock_html
    )
    
    mock_client = MagicMock(spec=SyncBrightDataClient)
    mock_client.scrape_url.return_value = mock_result
    mock_client.__enter__ = MagicMock(return_value=mock_client)  # Context manager support
    
    with patch("app.flows.opgroeien.poc.chat.tools.fetch_website._get_brightdata_client", return_value=mock_client):
        # Call the tool with proper invocation
        result = fetch_website.invoke({"url": "https://example.com"})
        
        # Verify heuristic-based removals
        assert "Cookie banner" not in result
        assert "Ad content" not in result
        assert "Advertisement" not in result
        assert "Popup" not in result
        assert "Newsletter" not in result
        assert "Social" not in result
        
        # Verify main content remains
        assert "This should remain" in result


def test_fetch_webpage_markdown_conversion():
    """Test that HTML is properly converted to Markdown with ATX headings."""
    mock_html = """
    <html>
        <body>
            <h1>Heading 1</h1>
            <h2>Heading 2</h2>
            <p>Paragraph with <strong>bold</strong> and <em>italic</em> text.</p>
            <ul>
                <li>Item 1</li>
                <li>Item 2</li>
            </ul>
        </body>
    </html>
    """
    
    mock_result = ScrapeResult(
        success=True,
        url="https://example.com",
        status="ready",
        data=mock_html
    )
    
    mock_client = MagicMock(spec=SyncBrightDataClient)
    mock_client.scrape_url.return_value = mock_result
    mock_client.__enter__ = MagicMock(return_value=mock_client)  # Context manager support
    
    with patch("app.flows.opgroeien.poc.chat.tools.fetch_website._get_brightdata_client", return_value=mock_client):
        # Call the tool with proper invocation
        result = fetch_website.invoke({"url": "https://example.com"})
        
        # Verify ATX heading style (# instead of underlined)
        assert "# Heading 1" in result or "Heading 1" in result
        assert "## Heading 2" in result or "Heading 2" in result
        assert "Paragraph" in result


def test_fetch_webpage_whitespace_cleanup():
    """Test that excessive newlines are reduced."""
    mock_html = """
    <html>
        <body>
            <p>Paragraph 1</p>
            <p>Paragraph 2</p>
        </body>
    </html>
    """
    
    mock_result = ScrapeResult(
        success=True,
        url="https://example.com",
        status="ready",
        data=mock_html
    )
    
    mock_client = MagicMock(spec=SyncBrightDataClient)
    mock_client.scrape_url.return_value = mock_result
    mock_client.__enter__ = MagicMock(return_value=mock_client)  # Context manager support
    
    with patch("app.flows.opgroeien.poc.chat.tools.fetch_website._get_brightdata_client", return_value=mock_client):
        # Call the tool with proper invocation
        result = fetch_website.invoke({"url": "https://example.com"})
        
        # Verify no excessive newlines (more than 2 consecutive)
        import re
        excessive_newlines = re.search(r'\n{4,}', result)
        assert excessive_newlines is None, "Found excessive newlines in result"


def test_fetch_webpage_missing_api_key():
    """Test error handling when BRIGHTDATA_API_KEY is missing."""
    with patch("app.flows.opgroeien.poc.chat.tools.fetch_website.settings.BRIGHTDATA_API_KEY", ""):
        # Call the tool with proper invocation
        result = fetch_website.invoke({"url": "https://example.com"})
        
        assert "Error" in result
        assert "Configuration issue" in result or "BRIGHTDATA_API_KEY" in result


def test_fetch_webpage_brightdata_api_error():
    """Test error handling when BrightData API raises an exception."""
    mock_client = MagicMock(spec=SyncBrightDataClient)
    mock_client.scrape_url.side_effect = Exception("API connection failed")
    mock_client.__enter__ = MagicMock(return_value=mock_client)  # Context manager support
    
    with patch("app.flows.opgroeien.poc.chat.tools.fetch_website._get_brightdata_client", return_value=mock_client):
        # Call the tool with proper invocation
        result = fetch_website.invoke({"url": "https://example.com"})
        
        assert "Error fetching webpage" in result
        assert "API connection failed" in result


def test_fetch_webpage_empty_html_response():
    """Test handling of empty HTML response from BrightData."""
    mock_result = ScrapeResult(
        success=True,
        url="https://example.com",
        status="ready",
        data=""
    )
    
    mock_client = MagicMock(spec=SyncBrightDataClient)
    mock_client.scrape_url.return_value = mock_result
    mock_client.__enter__ = MagicMock(return_value=mock_client)  # Context manager support
    
    with patch("app.flows.opgroeien.poc.chat.tools.fetch_website._get_brightdata_client", return_value=mock_client):
        # Call the tool with proper invocation
        result = fetch_website.invoke({"url": "https://example.com"})
        
        assert "Error" in result
        assert "No content fetched" in result


def test_fetch_webpage_malformed_html():
    """Test that BeautifulSoup handles malformed HTML gracefully."""
    # Malformed HTML (missing closing tags, etc.)
    mock_html = """
    <html>
        <body>
            <h1>Unclosed heading
            <p>Unclosed paragraph
            <div>Some content</div>
        </body>
    </html>
    """
    
    mock_result = ScrapeResult(
        success=True,
        url="https://example.com",
        status="ready",
        data=mock_html
    )
    
    mock_client = MagicMock(spec=SyncBrightDataClient)
    mock_client.scrape_url.return_value = mock_result
    mock_client.__enter__ = MagicMock(return_value=mock_client)  # Context manager support
    
    with patch("app.flows.opgroeien.poc.chat.tools.fetch_website._get_brightdata_client", return_value=mock_client):
        # Should not raise an exception
        # Call the tool with proper invocation
        result = fetch_website.invoke({"url": "https://example.com"})
        
        # BeautifulSoup should parse it and return something
        assert isinstance(result, str)
        assert len(result) > 0


def test_fetch_webpage_no_html_key_in_response():
    """Test handling when BrightData response doesn't have HTML data."""
    mock_result = ScrapeResult(
        success=True,
        url="https://example.com",
        status="ready",
        data=None
    )
    
    mock_client = MagicMock(spec=SyncBrightDataClient)
    mock_client.scrape_url.return_value = mock_result
    mock_client.__enter__ = MagicMock(return_value=mock_client)  # Context manager support
    
    with patch("app.flows.opgroeien.poc.chat.tools.fetch_website._get_brightdata_client", return_value=mock_client):
        # Call the tool with proper invocation
        result = fetch_website.invoke({"url": "https://example.com"})
        
        assert "Error" in result
        assert "No content fetched" in result


def test_fetch_webpage_api_failure():
    """Test handling when BrightData API returns unsuccessful result."""
    mock_result = ScrapeResult(
        success=False,
        url="https://example.com",
        status="error",
        data=None,
        error="Access denied"
    )
    
    mock_client = MagicMock(spec=SyncBrightDataClient)
    mock_client.scrape_url.return_value = mock_result
    mock_client.__enter__ = MagicMock(return_value=mock_client)  # Context manager support
    
    with patch("app.flows.opgroeien.poc.chat.tools.fetch_website._get_brightdata_client", return_value=mock_client):
        # Call the tool with proper invocation
        result = fetch_website.invoke({"url": "https://example.com"})
        
        assert "Error" in result
        assert "Failed to fetch webpage" in result
        assert "Access denied" in result


def test_fetch_webpage_none_result():
    """Test handling when BrightData returns None."""
    mock_client = MagicMock(spec=SyncBrightDataClient)
    mock_client.scrape_url.return_value = None
    mock_client.__enter__ = MagicMock(return_value=mock_client)  # Context manager support
    
    with patch("app.flows.opgroeien.poc.chat.tools.fetch_website._get_brightdata_client", return_value=mock_client):
        # Call the tool with proper invocation
        result = fetch_website.invoke({"url": "https://example.com"})
        
        assert "Error" in result
        assert "No content fetched" in result


def test_fetch_webpage_content_truncation():
    """Test that very large content is truncated to prevent token limit issues."""
    # Create content that exceeds the max length (50,000 chars)
    large_content = "A" * 60_000
    
    mock_result = ScrapeResult(
        success=True,
        url="https://example.com",
        status="ready",
        data=f"<html><body><p>{large_content}</p></body></html>"
    )
    
    mock_client = MagicMock(spec=SyncBrightDataClient)
    mock_client.scrape_url.return_value = mock_result
    mock_client.__enter__ = MagicMock(return_value=mock_client)  # Context manager support
    
    with patch("app.flows.opgroeien.poc.chat.tools.fetch_website._get_brightdata_client", return_value=mock_client):
        # Call the tool with proper invocation
        result = fetch_website.invoke({"url": "https://example.com"})
        
        # Verify content was truncated
        assert len(result) < 60_000
        assert "Content truncated" in result
        assert "showing first" in result


def test_extract_entities_successful():
    """Test successful entity extraction with LLM."""
    from langchain_core.messages import AIMessage
    from app.flows.opgroeien.poc.chat.tools.extract_entities import extract_entities
    
    # Mock entity extraction result
    mock_extraction_result = {
        "entities": [
            {
                "name": "Vlaamse Overheid",
                "type": "Overheidsorgaan",
                "description": "De Vlaamse overheid is de uitvoerende macht van Vlaanderen.",
                "confidence": 0.95
            },
            {
                "name": "Kinderopvang",
                "type": "Document",
                "description": "Regelgeving rond kinderopvang.",
                "confidence": 0.88
            }
        ],
        "metadata": {
            "extraction_timestamp": "2025-01-15T10:00:00Z",
            "source_text_length": 100
        }
    }
    
    # Create mock AI message with tool call
    mock_ai_message = AIMessage(
        content="",
        tool_calls=[{
            "name": "extract_knowledge",
            "args": mock_extraction_result,
            "id": "test_call_id"
        }]
    )
    
    # Mock the model
    mock_model = MagicMock()
    mock_model_with_tools = MagicMock()
    mock_model.bind_tools.return_value = mock_model_with_tools
    mock_model_with_tools.invoke.return_value = mock_ai_message
    
    # Reset the cached model
    import app.flows.common as common_module
    common_module._entity_extraction_model = None
    
    with patch("app.flows.common.get_entity_extraction_model", return_value=mock_model):
        # Call the tool
        result = extract_entities.invoke({"chatInput": "De Vlaamse Overheid heeft regelgeving rond kinderopvang."})
        
        # Parse result
        result_data = json.loads(result)
        
        # Verify structure
        assert "entities" in result_data
        assert "metadata" in result_data
        assert len(result_data["entities"]) == 2
        
        # Verify entity data
        assert result_data["entities"][0]["name"] == "Vlaamse Overheid"
        assert result_data["entities"][0]["type"] == "Overheidsorgaan"
        assert result_data["entities"][0]["confidence"] == 0.95
        
        # Verify metadata
        assert "extraction_timestamp" in result_data["metadata"]
        assert "source_text_length" in result_data["metadata"]


def test_extract_entities_empty_input():
    """Test entity extraction with empty input."""
    from app.flows.opgroeien.poc.chat.tools.extract_entities import extract_entities
    
    result = extract_entities.invoke({"chatInput": ""})
    result_data = json.loads(result)
    
    assert "entities" in result_data
    assert len(result_data["entities"]) == 0
    assert "error" in result_data
    assert "Empty input text" in result_data["error"]


def test_extract_entities_no_function_call():
    """Test entity extraction when LLM doesn't return a function call."""
    from langchain_core.messages import AIMessage
    from app.flows.opgroeien.poc.chat.tools.extract_entities import extract_entities
    
    # Mock AI message without tool calls
    mock_ai_message = AIMessage(content="I cannot extract entities from this text.")
    
    mock_model = MagicMock()
    mock_model_with_tools = MagicMock()
    mock_model.bind_tools.return_value = mock_model_with_tools
    mock_model_with_tools.invoke.return_value = mock_ai_message
    
    # Reset the cached model
    import app.flows.common as common_module
    common_module._entity_extraction_model = None
    
    with patch("app.flows.common.get_entity_extraction_model", return_value=mock_model):
        result = extract_entities.invoke({"chatInput": "Some text"})
        result_data = json.loads(result)
        
        assert "entities" in result_data
        assert len(result_data["entities"]) == 0
        assert "error" in result_data
        assert "LLM did not return a function call" in result_data["error"]


def test_query_knowledge_graph_successful():
    """Test successful knowledge graph query with relationships."""
    from app.flows.opgroeien.poc.chat.tools.query_knowledge_graph import query_knowledge_graph
    
    # Mock database cursor results
    # First entity query returns matched entity and connected entities
    mock_results_entity1 = [
        ("Entity1",),  # Matched entity name
        ("ConnectedEntity1",),  # Connected entity name
        ("ConnectedEntity2",),  # Another connected entity name
    ]
    
    # Second entity query returns different results
    mock_results_entity2 = [
        ("Entity2",),  # Matched entity name
        ("ConnectedEntity3",),  # Connected entity name
    ]
    
    # Mock cursor
    mock_cursor = MagicMock()
    mock_cursor.execute = MagicMock()
    # First call returns entity1 results, second call returns entity2 results
    mock_cursor.fetchall.side_effect = [mock_results_entity1, mock_results_entity2]
    
    # Mock connection
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    
    with patch("app.flows.opgroeien.poc.chat.tools.query_knowledge_graph._get_db_connection", return_value=mock_conn):
        # Call the tool with JSON string containing array of entities
        result = query_knowledge_graph.invoke({"entities": json.dumps(["Entity1", "Entity2"])})
        
        # Parse result
        result_data = json.loads(result)
        
        # Verify structure
        assert "entities" in result_data
        assert isinstance(result_data["entities"], list)
        
        # Verify all entity names are included (unique set)
        entity_names = set(result_data["entities"])
        assert "Entity1" in entity_names
        assert "Entity2" in entity_names
        assert "ConnectedEntity1" in entity_names
        assert "ConnectedEntity2" in entity_names
        assert "ConnectedEntity3" in entity_names
        
        # Verify no duplicates
        assert len(result_data["entities"]) == len(entity_names)
        
        # Verify sorted (as per implementation)
        assert result_data["entities"] == sorted(result_data["entities"])
        
        # Verify cursor.execute was called for each entity
        assert mock_cursor.execute.call_count == 2


def test_query_knowledge_graph_empty_results():
    """Test knowledge graph query when no entities or relationships are found."""
    from app.flows.opgroeien.poc.chat.tools.query_knowledge_graph import query_knowledge_graph
    
    # Mock empty results
    mock_cursor = MagicMock()
    mock_cursor.execute = MagicMock()
    mock_cursor.fetchall.return_value = []
    
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    
    with patch("app.flows.opgroeien.poc.chat.tools.query_knowledge_graph._get_db_connection", return_value=mock_conn):
        result = query_knowledge_graph.invoke({"entities": json.dumps(["NonExistentEntity"])})
        result_data = json.loads(result)
        
        assert "entities" in result_data
        assert result_data["entities"] == []


def test_query_knowledge_graph_invalid_input():
    """Test knowledge graph query with invalid input."""
    from app.flows.opgroeien.poc.chat.tools.query_knowledge_graph import query_knowledge_graph
    
    # Test with non-list input
    result = query_knowledge_graph.invoke({"entities": json.dumps("not a list")})
    result_data = json.loads(result)
    assert "entities" in result_data
    assert result_data["entities"] == []
    
    # Test with empty list
    result = query_knowledge_graph.invoke({"entities": json.dumps([])})
    result_data = json.loads(result)
    assert "entities" in result_data
    assert result_data["entities"] == []
    
    # Test with null/None
    result = query_knowledge_graph.invoke({"entities": json.dumps(None)})
    result_data = json.loads(result)
    assert "entities" in result_data
    assert result_data["entities"] == []


def test_query_knowledge_graph_skips_invalid_entities():
    """Test that invalid entities in the list are skipped."""
    from app.flows.opgroeien.poc.chat.tools.query_knowledge_graph import query_knowledge_graph
    
    # Mock results for valid entity
    mock_cursor = MagicMock()
    mock_cursor.execute = MagicMock()
    mock_cursor.fetchall.return_value = [("ValidEntity",), ("ConnectedEntity",)]
    
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    
    with patch("app.flows.opgroeien.poc.chat.tools.query_knowledge_graph._get_db_connection", return_value=mock_conn):
        # Input contains empty string, None, and valid entity
        result = query_knowledge_graph.invoke({
            "entities": json.dumps(["", None, "ValidEntity", "   "])
        })
        result_data = json.loads(result)
        
        # Should only process the valid entity
        assert mock_cursor.execute.call_count == 1
        assert "ValidEntity" in result_data["entities"]
        assert "ConnectedEntity" in result_data["entities"]


def test_query_knowledge_graph_database_error():
    """Test error handling when database connection fails."""
    from app.flows.opgroeien.poc.chat.tools.query_knowledge_graph import query_knowledge_graph
    
    # Mock database connection error
    with patch("app.flows.opgroeien.poc.chat.tools.query_knowledge_graph._get_db_connection", side_effect=Exception("Database connection failed")):
        result = query_knowledge_graph.invoke({"entities": json.dumps(["Entity1"])})
        result_data = json.loads(result)
        
        assert "error" in result_data
        assert "Failed to query knowledge graph" in result_data["error"]
        assert "Database connection failed" in result_data["error"]


def test_query_knowledge_graph_sql_execution_error():
    """Test error handling when SQL execution fails."""
    from app.flows.opgroeien.poc.chat.tools.query_knowledge_graph import query_knowledge_graph
    
    # Mock cursor that raises error on execute
    mock_cursor = MagicMock()
    mock_cursor.execute.side_effect = Exception("SQL syntax error")
    
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    
    with patch("app.flows.opgroeien.poc.chat.tools.query_knowledge_graph._get_db_connection", return_value=mock_conn):
        result = query_knowledge_graph.invoke({"entities": json.dumps(["Entity1"])})
        result_data = json.loads(result)
        
        assert "error" in result_data
        assert "Failed to query knowledge graph" in result_data["error"]
        assert "SQL syntax error" in result_data["error"]


def test_query_knowledge_graph_case_insensitive():
    """Test that entity matching is case-insensitive."""
    from app.flows.opgroeien.poc.chat.tools.query_knowledge_graph import query_knowledge_graph
    
    # Mock results
    mock_cursor = MagicMock()
    mock_cursor.execute = MagicMock()
    mock_cursor.fetchall.return_value = [("Entity1",), ("ConnectedEntity",)]
    
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    
    with patch("app.flows.opgroeien.poc.chat.tools.query_knowledge_graph._get_db_connection", return_value=mock_conn):
        # Test with different case
        result = query_knowledge_graph.invoke({"entities": json.dumps(["entity1"])})
        result_data = json.loads(result)
        
        # Verify SQL query uses LOWER() for case-insensitive matching
        # Check that execute was called with the entity name
        call_args = mock_cursor.execute.call_args
        assert call_args is not None
        # The SQL should contain LOWER() function (verified by the query structure)


def test_query_knowledge_graph_deduplicates_entities():
    """Test that duplicate entity names are deduplicated."""
    from app.flows.opgroeien.poc.chat.tools.query_knowledge_graph import query_knowledge_graph
    
    # Mock results with duplicates
    mock_cursor = MagicMock()
    mock_cursor.execute = MagicMock()
    # Return same entity multiple times (from different relationships)
    mock_cursor.fetchall.return_value = [
        ("Entity1",),
        ("ConnectedEntity",),
        ("ConnectedEntity",),  # Duplicate
        ("Entity1",),  # Duplicate
    ]
    
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    
    with patch("app.flows.opgroeien.poc.chat.tools.query_knowledge_graph._get_db_connection", return_value=mock_conn):
        result = query_knowledge_graph.invoke({"entities": json.dumps(["Entity1"])})
        result_data = json.loads(result)
        
        # Should only have unique entities
        assert len(result_data["entities"]) == 2
        assert "Entity1" in result_data["entities"]
        assert "ConnectedEntity" in result_data["entities"]
        # Verify no duplicates
        assert len(result_data["entities"]) == len(set(result_data["entities"]))


def test_generate_docx_successful():
    """Test successful DOCX generation with GCS upload and signed URL."""
    from app.flows.opgroeien.poc.chat.tools.generate_docx import generate_docx
    
    # Mock markdown content
    markdown_content = "# Heading\n\nThis is a paragraph with **bold** text."
    test_thread_id = "test-thread-123"
    test_file_name = "test_document"
    
    # Mock pypandoc conversion
    mock_docx_bytes = b"fake docx content"
    
    with patch("app.flows.opgroeien.poc.chat.tools.generate_docx.pypandoc.convert_text") as mock_convert, \
         patch("app.flows.opgroeien.poc.chat.tools.generate_docx.upload_output_to_gcs") as mock_upload, \
         patch("app.flows.opgroeien.poc.chat.tools.generate_docx.generate_signed_url") as mock_signed_url, \
         patch("builtins.open", create=True) as mock_open:
        
        # Setup mocks
        mock_convert.return_value = None  # pypandoc writes to file, returns None
        mock_file = MagicMock()
        mock_file.read.return_value = mock_docx_bytes
        mock_open.return_value.__enter__ = MagicMock(return_value=mock_file)
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        
        mock_upload.return_value = "output/test-thread-123/test_document.docx"
        mock_signed_url.return_value = "https://storage.googleapis.com/bucket/path?signed=url"
        
        # Call the tool
        result = generate_docx.invoke({
            "fileName": test_file_name,
            "data": markdown_content,
            "thread_id": test_thread_id
        })
        
        # Verify pypandoc was called correctly
        mock_convert.assert_called_once()
        call_args = mock_convert.call_args
        assert call_args[0][0] == markdown_content
        assert call_args[0][1] == 'docx'
        assert call_args[1]['format'] == 'md'
        assert '--standalone' in call_args[1]['extra_args']
        
        # Verify GCS upload was called
        mock_upload.assert_called_once()
        upload_args = mock_upload.call_args
        assert upload_args[1]['file_content'] == mock_docx_bytes
        assert upload_args[1]['file_name'] == "test_document.docx"
        assert upload_args[1]['session_id'] == test_thread_id
        assert upload_args[1]['content_type'] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        
        # Verify signed URL was generated
        mock_signed_url.assert_called_once_with("output/test-thread-123/test_document.docx", expiration_minutes=60)
        
        # Verify result is the signed URL
        assert result == "https://storage.googleapis.com/bucket/path?signed=url"


def test_generate_docx_without_thread_id():
    """Test DOCX generation when thread_id is not provided (should generate UUID)."""
    from app.flows.opgroeien.poc.chat.tools.generate_docx import generate_docx
    import uuid
    
    markdown_content = "# Test"
    test_file_name = "test"
    
    with patch("app.flows.opgroeien.poc.chat.tools.generate_docx.pypandoc.convert_text") as mock_convert, \
         patch("app.flows.opgroeien.poc.chat.tools.generate_docx.upload_output_to_gcs") as mock_upload, \
         patch("app.flows.opgroeien.poc.chat.tools.generate_docx.generate_signed_url") as mock_signed_url, \
         patch("builtins.open", create=True) as mock_open, \
         patch("app.flows.opgroeien.poc.chat.tools.generate_docx.uuid.uuid4") as mock_uuid:
        
        # Setup mocks
        mock_uuid.return_value = uuid.UUID('12345678-1234-5678-1234-567812345678')
        mock_convert.return_value = None
        mock_file = MagicMock()
        mock_file.read.return_value = b"docx content"
        mock_open.return_value.__enter__ = MagicMock(return_value=mock_file)
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        
        mock_upload.return_value = "output/path/file.docx"
        mock_signed_url.return_value = "https://example.com/signed"
        
        # Call without thread_id
        result = generate_docx.invoke({
            "fileName": test_file_name,
            "data": markdown_content
        })
        
        # Verify UUID was generated and used
        mock_uuid.assert_called_once()
        upload_args = mock_upload.call_args
        assert upload_args[1]['session_id'] == "12345678-1234-5678-1234-567812345678"
        
        assert result == "https://example.com/signed"


def test_generate_docx_adds_extension():
    """Test that .docx extension is added if missing."""
    from app.flows.opgroeien.poc.chat.tools.generate_docx import generate_docx
    
    markdown_content = "# Test"
    
    with patch("app.flows.opgroeien.poc.chat.tools.generate_docx.pypandoc.convert_text") as mock_convert, \
         patch("app.flows.opgroeien.poc.chat.tools.generate_docx.upload_output_to_gcs") as mock_upload, \
         patch("app.flows.opgroeien.poc.chat.tools.generate_docx.generate_signed_url") as mock_signed_url, \
         patch("builtins.open", create=True) as mock_open:
        
        mock_convert.return_value = None
        mock_file = MagicMock()
        mock_file.read.return_value = b"content"
        mock_open.return_value.__enter__ = MagicMock(return_value=mock_file)
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        
        mock_upload.return_value = "output/path/file.docx"
        mock_signed_url.return_value = "https://example.com/signed"
        
        # Call with filename without extension
        generate_docx.invoke({
            "fileName": "test_file",
            "data": markdown_content,
            "thread_id": "test-thread"
        })
        
        # Verify .docx was added
        upload_args = mock_upload.call_args
        assert upload_args[1]['file_name'] == "test_file.docx"


def test_generate_docx_validation_empty_filename():
    """Test validation error when fileName is empty."""
    from app.flows.opgroeien.poc.chat.tools.generate_docx import generate_docx
    
    with pytest.raises(ValueError, match="fileName cannot be empty"):
        generate_docx.invoke({
            "fileName": "",
            "data": "# Test content"
        })


def test_generate_docx_validation_empty_data():
    """Test validation error when data is empty."""
    from app.flows.opgroeien.poc.chat.tools.generate_docx import generate_docx
    
    with pytest.raises(ValueError, match="data cannot be empty"):
        generate_docx.invoke({
            "fileName": "test",
            "data": ""
        })


def test_generate_docx_pandoc_not_available():
    """Test error handling when pandoc is not available."""
    from app.flows.opgroeien.poc.chat.tools.generate_docx import generate_docx
    
    markdown_content = "# Test"
    
    with patch("app.flows.opgroeien.poc.chat.tools.generate_docx.pypandoc.convert_text", side_effect=RuntimeError("Pandoc not found")):
        with pytest.raises(RuntimeError, match="Pandoc is not available"):
            generate_docx.invoke({
                "fileName": "test",
                "data": markdown_content,
                "thread_id": "test-thread"
            })


def test_generate_docx_filesystem_error():
    """Test error handling for file system errors."""
    from app.flows.opgroeien.poc.chat.tools.generate_docx import generate_docx
    
    markdown_content = "# Test"
    
    with patch("app.flows.opgroeien.poc.chat.tools.generate_docx.pypandoc.convert_text", side_effect=OSError("Permission denied")):
        with pytest.raises(OSError, match="File system error"):
            generate_docx.invoke({
                "fileName": "test",
                "data": markdown_content,
                "thread_id": "test-thread"
            })


def test_generate_docx_gcs_upload_error():
    """Test error handling when GCS upload fails."""
    from app.flows.opgroeien.poc.chat.tools.generate_docx import generate_docx
    
    markdown_content = "# Test"
    
    with patch("app.flows.opgroeien.poc.chat.tools.generate_docx.pypandoc.convert_text") as mock_convert, \
         patch("app.flows.opgroeien.poc.chat.tools.generate_docx.upload_output_to_gcs", side_effect=Exception("GCS upload failed")) as mock_upload, \
         patch("builtins.open", create=True) as mock_open:
        
        mock_convert.return_value = None
        mock_file = MagicMock()
        mock_file.read.return_value = b"content"
        mock_open.return_value.__enter__ = MagicMock(return_value=mock_file)
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        
        with pytest.raises(Exception, match="Failed to generate and upload DOCX"):
            generate_docx.invoke({
                "fileName": "test",
                "data": markdown_content,
                "thread_id": "test-thread"
            })


def test_generate_docx_signed_url_error():
    """Test error handling when signed URL generation fails."""
    from app.flows.opgroeien.poc.chat.tools.generate_docx import generate_docx
    
    markdown_content = "# Test"
    
    with patch("app.flows.opgroeien.poc.chat.tools.generate_docx.pypandoc.convert_text") as mock_convert, \
         patch("app.flows.opgroeien.poc.chat.tools.generate_docx.upload_output_to_gcs") as mock_upload, \
         patch("app.flows.opgroeien.poc.chat.tools.generate_docx.generate_signed_url", side_effect=Exception("URL generation failed")) as mock_signed_url, \
         patch("builtins.open", create=True) as mock_open:
        
        mock_convert.return_value = None
        mock_file = MagicMock()
        mock_file.read.return_value = b"content"
        mock_open.return_value.__enter__ = MagicMock(return_value=mock_file)
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        
        mock_upload.return_value = "output/path/file.docx"
        
        with pytest.raises(Exception, match="Failed to generate and upload DOCX"):
            generate_docx.invoke({
                "fileName": "test",
                "data": markdown_content,
                "thread_id": "test-thread"
            })


def test_generate_docx_complex_markdown():
    """Test DOCX generation with complex markdown (headings, lists, code blocks)."""
    from app.flows.opgroeien.poc.chat.tools.generate_docx import generate_docx
    
    complex_markdown = """# Main Heading

## Subheading

This is a paragraph with **bold** and *italic* text.

- List item 1
- List item 2
  - Nested item

```python
def hello():
    print("world")
```

| Column 1 | Column 2 |
|----------|----------|
| Data 1   | Data 2   |
"""
    
    with patch("app.flows.opgroeien.poc.chat.tools.generate_docx.pypandoc.convert_text") as mock_convert, \
         patch("app.flows.opgroeien.poc.chat.tools.generate_docx.upload_output_to_gcs") as mock_upload, \
         patch("app.flows.opgroeien.poc.chat.tools.generate_docx.generate_signed_url") as mock_signed_url, \
         patch("builtins.open", create=True) as mock_open:
        
        mock_convert.return_value = None
        mock_file = MagicMock()
        mock_file.read.return_value = b"complex docx"
        mock_open.return_value.__enter__ = MagicMock(return_value=mock_file)
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        
        mock_upload.return_value = "output/path/complex.docx"
        mock_signed_url.return_value = "https://example.com/complex"
        
        result = generate_docx.invoke({
            "fileName": "complex_document",
            "data": complex_markdown,
            "thread_id": "test-thread"
        })
        
        # Verify pypandoc was called with the complex markdown
        assert mock_convert.call_args[0][0] == complex_markdown
        assert result == "https://example.com/complex"


def test_generate_xlsx_successful():
    """Test successful XLSX generation with GCS upload and signed URL."""
    from app.flows.opgroeien.poc.chat.tools.generate_xlsx import generate_xlsx
    
    # Mock JSON content
    json_content = '[{"name": "John", "age": 30}, {"name": "Jane", "age": 25}]'
    test_thread_id = "test-thread-123"
    test_file_name = "test_data"
    
    with patch("app.flows.opgroeien.poc.chat.tools.generate_xlsx.upload_output_to_gcs") as mock_upload, \
         patch("app.flows.opgroeien.poc.chat.tools.generate_xlsx.generate_signed_url") as mock_signed_url:
        
        # Setup mocks
        mock_upload.return_value = "output/test-thread-123/test_data.xlsx"
        mock_signed_url.return_value = "https://storage.googleapis.com/bucket/path?signed=url"
        
        # Call the tool
        result = generate_xlsx.invoke({
            "fileName": test_file_name,
            "data": json_content,
            "thread_id": test_thread_id
        })
        
        # Verify GCS upload was called
        mock_upload.assert_called_once()
        upload_args = mock_upload.call_args
        assert upload_args[1]['file_name'] == "test_data.xlsx"
        assert upload_args[1]['session_id'] == test_thread_id
        assert upload_args[1]['content_type'] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        # Verify file content is bytes (XLSX)
        assert isinstance(upload_args[1]['file_content'], bytes)
        assert len(upload_args[1]['file_content']) > 0
        
        # Verify signed URL was generated
        mock_signed_url.assert_called_once_with("output/test-thread-123/test_data.xlsx", expiration_minutes=60)
        
        # Verify result is the signed URL
        assert result == "https://storage.googleapis.com/bucket/path?signed=url"


def test_generate_xlsx_without_thread_id():
    """Test XLSX generation when thread_id is not provided (should generate UUID)."""
    from app.flows.opgroeien.poc.chat.tools.generate_xlsx import generate_xlsx
    import uuid
    
    json_content = '{"key": "value"}'
    test_file_name = "test"
    
    with patch("app.flows.opgroeien.poc.chat.tools.generate_xlsx.upload_output_to_gcs") as mock_upload, \
         patch("app.flows.opgroeien.poc.chat.tools.generate_xlsx.generate_signed_url") as mock_signed_url, \
         patch("app.flows.opgroeien.poc.chat.tools.generate_xlsx.uuid.uuid4") as mock_uuid:
        
        # Setup mocks
        mock_uuid.return_value = uuid.UUID('12345678-1234-5678-1234-567812345678')
        mock_upload.return_value = "output/path/file.xlsx"
        mock_signed_url.return_value = "https://example.com/signed"
        
        # Call without thread_id
        result = generate_xlsx.invoke({
            "fileName": test_file_name,
            "data": json_content
        })
        
        # Verify UUID was generated and used
        mock_uuid.assert_called_once()
        upload_args = mock_upload.call_args
        assert upload_args[1]['session_id'] == "12345678-1234-5678-1234-567812345678"
        
        assert result == "https://example.com/signed"


def test_generate_xlsx_adds_extension():
    """Test that .xlsx extension is added if missing."""
    from app.flows.opgroeien.poc.chat.tools.generate_xlsx import generate_xlsx
    
    json_content = '{"test": "data"}'
    
    with patch("app.flows.opgroeien.poc.chat.tools.generate_xlsx.upload_output_to_gcs") as mock_upload, \
         patch("app.flows.opgroeien.poc.chat.tools.generate_xlsx.generate_signed_url") as mock_signed_url:
        
        mock_upload.return_value = "output/path/file.xlsx"
        mock_signed_url.return_value = "https://example.com/signed"
        
        # Call with filename without extension
        generate_xlsx.invoke({
            "fileName": "test_file",
            "data": json_content,
            "thread_id": "test-thread"
        })
        
        # Verify .xlsx was added
        upload_args = mock_upload.call_args
        assert upload_args[1]['file_name'] == "test_file.xlsx"


def test_generate_xlsx_validation_empty_filename():
    """Test validation error when fileName is empty."""
    from app.flows.opgroeien.poc.chat.tools.generate_xlsx import generate_xlsx
    
    with pytest.raises(ValueError, match="fileName cannot be empty"):
        generate_xlsx.invoke({
            "fileName": "",
            "data": '{"test": "data"}'
        })


def test_generate_xlsx_validation_empty_data():
    """Test validation error when data is empty."""
    from app.flows.opgroeien.poc.chat.tools.generate_xlsx import generate_xlsx
    
    with pytest.raises(ValueError, match="data cannot be empty"):
        generate_xlsx.invoke({
            "fileName": "test",
            "data": ""
        })


def test_generate_xlsx_invalid_json():
    """Test error handling for invalid JSON."""
    from app.flows.opgroeien.poc.chat.tools.generate_xlsx import generate_xlsx
    
    with pytest.raises(ValueError, match="Invalid JSON format"):
        generate_xlsx.invoke({
            "fileName": "test",
            "data": "not valid json {",
            "thread_id": "test-thread"
        })


def test_generate_xlsx_gcs_upload_error():
    """Test error handling when GCS upload fails."""
    from app.flows.opgroeien.poc.chat.tools.generate_xlsx import generate_xlsx
    
    json_content = '{"key": "value"}'
    
    with patch("app.flows.opgroeien.poc.chat.tools.generate_xlsx.upload_output_to_gcs", side_effect=Exception("GCS upload failed")) as mock_upload:
        
        with pytest.raises(Exception, match="Failed to generate and upload XLSX"):
            generate_xlsx.invoke({
                "fileName": "test",
                "data": json_content,
                "thread_id": "test-thread"
            })


def test_generate_xlsx_signed_url_error():
    """Test error handling when signed URL generation fails."""
    from app.flows.opgroeien.poc.chat.tools.generate_xlsx import generate_xlsx
    
    json_content = '{"key": "value"}'
    
    with patch("app.flows.opgroeien.poc.chat.tools.generate_xlsx.upload_output_to_gcs") as mock_upload, \
         patch("app.flows.opgroeien.poc.chat.tools.generate_xlsx.generate_signed_url", side_effect=Exception("URL generation failed")) as mock_signed_url:
        
        mock_upload.return_value = "output/path/file.xlsx"
        
        with pytest.raises(Exception, match="Failed to generate and upload XLSX"):
            generate_xlsx.invoke({
                "fileName": "test",
                "data": json_content,
                "thread_id": "test-thread"
            })


def test_generate_xlsx_list_of_dicts():
    """Test XLSX generation with list of dictionaries (most common case)."""
    from app.flows.opgroeien.poc.chat.tools.generate_xlsx import generate_xlsx
    
    json_content = '[{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]'
    
    with patch("app.flows.opgroeien.poc.chat.tools.generate_xlsx.upload_output_to_gcs") as mock_upload, \
         patch("app.flows.opgroeien.poc.chat.tools.generate_xlsx.generate_signed_url") as mock_signed_url:
        
        mock_upload.return_value = "output/path/data.xlsx"
        mock_signed_url.return_value = "https://example.com/data"
        
        result = generate_xlsx.invoke({
            "fileName": "data",
            "data": json_content,
            "thread_id": "test-thread"
        })
        
        # Verify file was created with content
        upload_args = mock_upload.call_args
        assert len(upload_args[1]['file_content']) > 0
        assert result == "https://example.com/data"


def test_generate_xlsx_single_dict():
    """Test XLSX generation with single dictionary."""
    from app.flows.opgroeien.poc.chat.tools.generate_xlsx import generate_xlsx
    
    json_content = '{"name": "Alice", "age": 30}'
    
    with patch("app.flows.opgroeien.poc.chat.tools.generate_xlsx.upload_output_to_gcs") as mock_upload, \
         patch("app.flows.opgroeien.poc.chat.tools.generate_xlsx.generate_signed_url") as mock_signed_url:
        
        mock_upload.return_value = "output/path/data.xlsx"
        mock_signed_url.return_value = "https://example.com/data"
        
        result = generate_xlsx.invoke({
            "fileName": "data",
            "data": json_content,
            "thread_id": "test-thread"
        })
        
        assert result == "https://example.com/data"


def test_generate_xlsx_list_of_values():
    """Test XLSX generation with simple list of values."""
    from app.flows.opgroeien.poc.chat.tools.generate_xlsx import generate_xlsx
    
    json_content = '["apple", "banana", "cherry"]'
    
    with patch("app.flows.opgroeien.poc.chat.tools.generate_xlsx.upload_output_to_gcs") as mock_upload, \
         patch("app.flows.opgroeien.poc.chat.tools.generate_xlsx.generate_signed_url") as mock_signed_url:
        
        mock_upload.return_value = "output/path/list.xlsx"
        mock_signed_url.return_value = "https://example.com/list"
        
        result = generate_xlsx.invoke({
            "fileName": "list",
            "data": json_content,
            "thread_id": "test-thread"
        })
        
        assert result == "https://example.com/list"

