"""
Tool for fetching website content from opgroeien.be or vlaanderen.be.
"""
from __future__ import annotations

import re

import structlog
from bs4 import BeautifulSoup
from brightdata import SyncBrightDataClient
from langchain_core.tools import StructuredTool
from markdownify import markdownify as md

from app.config import settings

logger = structlog.get_logger(__name__)

# Cache BrightData client
# Note: SyncBrightDataClient is not thread-safe, but we use it in a single-threaded tool execution context
_brightdata_client: SyncBrightDataClient | None = None


def _get_brightdata_client() -> SyncBrightDataClient:
    """Get or create cached BrightData sync client.
    
    Uses SyncBrightDataClient for synchronous scraping as per official SDK docs:
    https://github.com/brightdata/sdk-python/blob/main/docs/sync_client.md
    
    Note: The client is cached globally. SyncBrightDataClient uses a persistent
    event loop internally, so we initialize it once and reuse it.
    """
    global _brightdata_client
    if _brightdata_client is None:
        if not settings.BRIGHTDATA_API_KEY:
            raise ValueError("BRIGHTDATA_API_KEY is required but not set")
        # Initialize sync client with token and enter context manager
        # This initializes the persistent event loop
        _brightdata_client = SyncBrightDataClient(token=settings.BRIGHTDATA_API_KEY)
        _brightdata_client.__enter__()
    return _brightdata_client


def _fetch_website_impl(url: str) -> str:
    try:
        # Get BrightData client
        client = _get_brightdata_client()
        
        # Track timing for Bright Data usage
        import time
        start_time = time.perf_counter()
        
        # 1. Fetch RAW HTML using BrightData API
        # We need the HTML structure to find and kill specific tags.
        # Use scrape_url method per official BrightData SDK sync client docs:
        # https://github.com/brightdata/sdk-python/blob/main/docs/sync_client.md
        result = client.scrape_url(url)
        
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        
        # Extract cost if available from result
        cost = None
        if hasattr(result, "cost") and result.cost is not None:
            cost = float(result.cost)
        elif isinstance(result, dict) and "cost" in result:
            cost = float(result["cost"])
        
        # Record Bright Data usage metrics
        try:
            from app.api.observability import record_brightdata_usage
            record_brightdata_usage(
                duration_ms=duration_ms,
                cost=cost,
            )
        except Exception:
            # Don't fail if observability is not available
            pass
        
        if result is None:
            logger.warning(
                "fetch_webpage_empty_response",
                url=url,
                message="No result returned from BrightData",
            )
            return "Error: No content fetched."
        
        if not result.success:
            error_msg = result.error or "Unknown error"
            logger.warning(
                "fetch_webpage_api_error",
                url=url,
                error=error_msg,
                status=result.status,
            )
            return f"Error: Failed to fetch webpage - {error_msg}"
        
        # Extract HTML from result data
        # The data field contains the HTML content (may be string or dict)
        html_content = result.data
        if isinstance(html_content, dict):
            # If data is a dict, try to get 'html' key
            html_content = html_content.get('html', '') or html_content.get('body', '') or str(html_content)
        elif not isinstance(html_content, str):
            # Convert to string if it's not already
            html_content = str(html_content) if html_content else ''
        
        if not html_content:
            logger.warning(
                "fetch_webpage_empty_response",
                url=url,
                message="No HTML content in BrightData response",
            )
            return "Error: No content fetched."
        
        # 2. Initialize BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 3. Surgical Cleaning (The "BS4" Step)
        # Remove tags that are semantically useless for an AI agent
        tags_to_remove = [
            'nav',          # Navigation bars
            'footer',       # Footers
            'script',       # Javascript
            'style',        # CSS
            'noscript',     # Fallback content
            'iframe',       # Ads/Embeds
            'svg',          # Icons
            'aside',        # Sidebars (often ads or "related links")
            'form',         # Search bars/inputs
            'button'        # UI elements
        ]
        
        for tag in tags_to_remove:
            for element in soup.find_all(tag):
                element.decompose()  # Completely destroys the tag and its content
        
        # 3b. Optional: Remove elements by class/id heuristics
        # This catches things like <div class="cookie-banner">
        keywords = ['cookie', 'ad-', 'advert', 'popup', 'newsletter', 'social']
        for tag in soup.find_all(True):
            # Check class and id attributes
            attr_str = str(tag.get('class', '')) + str(tag.get('id', ''))
            if any(x in attr_str.lower() for x in keywords):
                tag.decompose()
        
        # 4. Convert to Markdown
        # heading_style="ATX" ensures # style headers instead of underlined
        cleaned_markdown = md(str(soup), heading_style="ATX", strip=['a', 'img'])
        
        # 5. Final whitespace cleanup
        cleaned_markdown = re.sub(r'\n{3,}', '\n\n', cleaned_markdown).strip()
        
        # 6. Truncate content to prevent token limit issues
        # Limit to ~50,000 characters (~12,500 tokens) to stay well under LLM limits
        MAX_CONTENT_LENGTH = 50_000
        original_length = len(cleaned_markdown)
        if original_length > MAX_CONTENT_LENGTH:
            # Truncate to max length, preserving word boundaries where possible
            truncated = cleaned_markdown[:MAX_CONTENT_LENGTH]
            # Try to cut at a newline or space to avoid cutting words
            last_newline = truncated.rfind('\n')
            last_space = truncated.rfind(' ')
            cut_point = max(last_newline, last_space) if last_newline > MAX_CONTENT_LENGTH * 0.9 or last_space > MAX_CONTENT_LENGTH * 0.9 else MAX_CONTENT_LENGTH
            cleaned_markdown = cleaned_markdown[:cut_point].rstrip()
            cleaned_markdown += f"\n\n[Content truncated: showing first {len(cleaned_markdown):,} of {original_length:,} characters]"
            
            logger.warning(
                "fetch_webpage_truncated",
                url=url,
                original_length=original_length,
                truncated_length=len(cleaned_markdown),
            )
        
        logger.info(
            "fetch_webpage_success",
            url=url,
            markdown_length=len(cleaned_markdown),
        )
        
        return cleaned_markdown
        
    except ValueError as e:
        # Missing API key
        logger.error(
            "fetch_webpage_config_error",
            url=url,
            error=str(e),
            error_type=type(e).__name__,
        )
        return f"Error: Configuration issue - {str(e)}"
    except Exception as e:
        logger.error(
            "fetch_webpage_failed",
            url=url,
            error=str(e),
            error_type=type(e).__name__,
        )
        return f"Error fetching webpage: {str(e)}"


# Create tool with name "fetch_website"
fetch_website = StructuredTool.from_function(
    func=_fetch_website_impl,
    name="fetch_website",
    description="Fetches the current content of a webpage and converts it to Markdown. The tool automatically removes navigation elements, footers, scripts, and other non-content elements. Use this tool when you need current information from a website, for example to validate information, verify facts, or retrieve the most recent version of a document or page. Provide the full URL (including https://). The output is a clean Markdown version of the main content of the page.",
)
