"""
User thread management for tracking chat threads per user.

Provides functions to create, update, and query user threads in the database.
"""
from __future__ import annotations

from typing import Any

import structlog

from app.api.database import get_pool

logger = structlog.get_logger(__name__)


def generate_thread_title(message: str, max_length: int = 70) -> str | None:
    """
    Generate a thread title from the first user message.
    
    Truncates the message to a reasonable length, attempting to break at word boundaries.
    Returns None if the message is empty or only whitespace.
    
    Args:
        message: The first user message content
        max_length: Maximum length for the title (default: 70)
        
    Returns:
        Short title string or None if message is empty
    """
    if not message:
        return None
    
    # Strip leading/trailing whitespace
    stripped = message.strip()
    
    if not stripped:
        return None
    
    # If message is already short enough, return as-is
    if len(stripped) <= max_length:
        return stripped
    
    # Try to truncate at word boundary
    truncated = stripped[:max_length]
    last_space = truncated.rfind(' ')
    
    # If we found a space in the last 20% of the truncated text, use it
    if last_space > max_length * 0.8:
        truncated = truncated[:last_space].rstrip()
    
    # Add ellipsis if we truncated
    return truncated + "..."


async def thread_exists(thread_id: str) -> bool:
    """
    Check if a thread exists in the database.
    
    Args:
        thread_id: Thread UUID as string
        
    Returns:
        True if thread exists, False otherwise
        
    Raises:
        RuntimeError: If pool is not initialized
        Exception: If database operation fails
    """
    pool = get_pool()
    
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT EXISTS(
                        SELECT 1 FROM hit8.user_threads
                        WHERE thread_id = %s::uuid
                    )
                    """,
                    (thread_id,),
                )
                result = await cur.fetchone()
                return result[0] if result else False
    except Exception as e:
        logger.error(
            "thread_exists_check_failed",
            thread_id=thread_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise


async def update_last_accessed(thread_id: str) -> None:
    """
    Update the last_accessed_at timestamp for a thread.
    
    Args:
        thread_id: Thread UUID as string
        
    Raises:
        RuntimeError: If pool is not initialized
        Exception: If database operation fails
    """
    pool = get_pool()
    
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE hit8.user_threads
                    SET last_accessed_at = NOW()
                    WHERE thread_id = %s::uuid
                    """,
                    (thread_id,),
                )
                
        logger.debug(
            "thread_last_accessed_updated",
            thread_id=thread_id,
        )
    except Exception as e:
        logger.error(
            "thread_last_accessed_update_failed",
            thread_id=thread_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise


async def upsert_thread(thread_id: str, user_id: str, title: str | None = None, flow: str | None = None) -> None:
    """
    Upsert a thread record - create if it doesn't exist, update last_accessed_at if it does.
    
    Uses INSERT ... ON CONFLICT DO UPDATE to handle both new and existing threads
    in a single operation. This ensures threads are always created when they don't exist,
    and last_accessed_at is always updated.
    
    Args:
        thread_id: Thread UUID as string
        user_id: User identifier
        title: Optional thread title (defaults to None, only set on insert)
        flow: Optional flow identifier (format: "{org}.{project}.{flow}", e.g., "opgroeien.poc.chat")
        
    Raises:
        RuntimeError: If pool is not initialized
        Exception: If database operation fails
    """
    pool = get_pool()
    
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                # If title is provided, update it on conflict if current title is NULL
                if title is not None:
                    await cur.execute(
                        """
                        INSERT INTO hit8.user_threads (thread_id, user_id, title, flow, created_at, last_accessed_at)
                        VALUES (%s::uuid, %s, %s, %s, NOW(), NOW())
                        ON CONFLICT (thread_id) 
                        DO UPDATE SET 
                            last_accessed_at = NOW(),
                            title = COALESCE(user_threads.title, EXCLUDED.title),
                            flow = COALESCE(user_threads.flow, EXCLUDED.flow)
                        """,
                        (thread_id, user_id, title, flow),
                    )
                else:
                    await cur.execute(
                        """
                        INSERT INTO hit8.user_threads (thread_id, user_id, title, flow, created_at, last_accessed_at)
                        VALUES (%s::uuid, %s, %s, %s, NOW(), NOW())
                        ON CONFLICT (thread_id) 
                        DO UPDATE SET 
                            last_accessed_at = NOW(),
                            flow = COALESCE(user_threads.flow, EXCLUDED.flow)
                        """,
                        (thread_id, user_id, title, flow),
                    )
                
        logger.debug(
            "thread_upserted",
            thread_id=thread_id,
            user_id=user_id,
            has_title=title is not None,
            title_provided=title,
            flow=flow,
        )
    except Exception as e:
        logger.error(
            "thread_upsert_failed",
            thread_id=thread_id,
            user_id=user_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise


async def get_user_threads(user_id: str, flow: str | None = None) -> list[dict[str, Any]]:
    """
    Get all threads for a user, ordered by last_accessed_at descending.
    
    Args:
        user_id: User identifier
        flow: Optional flow identifier to filter by (format: "{org}.{project}.{flow}")
        
    Returns:
        List of thread dictionaries with keys:
        - thread_id (str)
        - user_id (str)
        - title (str | None)
        - flow (str | None)
        - created_at (str, ISO format)
        - last_accessed_at (str, ISO format)
        
    Raises:
        RuntimeError: If pool is not initialized
        Exception: If database operation fails
    """
    pool = get_pool()
    
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                if flow is not None:
                    await cur.execute(
                        """
                        SELECT thread_id, user_id, title, flow, created_at, last_accessed_at
                        FROM hit8.user_threads
                        WHERE user_id = %s AND flow = %s
                        ORDER BY last_accessed_at DESC
                        """,
                        (user_id, flow),
                    )
                else:
                    await cur.execute(
                        """
                        SELECT thread_id, user_id, title, flow, created_at, last_accessed_at
                        FROM hit8.user_threads
                        WHERE user_id = %s
                        ORDER BY last_accessed_at DESC
                        """,
                        (user_id,),
                    )
                
                rows = await cur.fetchall()
                
                threads = []
                for row in rows:
                    thread_id, user_id_val, title, flow_val, created_at, last_accessed_at = row
                    threads.append({
                        "thread_id": str(thread_id),
                        "user_id": user_id_val,
                        "title": title,
                        "flow": flow_val,
                        "created_at": created_at.isoformat() if created_at else None,
                        "last_accessed_at": last_accessed_at.isoformat() if last_accessed_at else None,
                    })
                
        logger.debug(
            "user_threads_retrieved",
            user_id=user_id,
            thread_count=len(threads),
            flow=flow,
        )
        
        return threads
    except Exception as e:
        logger.error(
            "user_threads_retrieval_failed",
            user_id=user_id,
            flow=flow,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise
