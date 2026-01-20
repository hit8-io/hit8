"""
Maintenance script to clean up LangGraph checkpoints and user_threads.

Keeps only the latest checkpoint for the most recently accessed thread.
All other checkpoints and threads are deleted.

This script is interactive - it shows a preview and asks for confirmation.

Run from project root with:
    cd backend && uv run python -m app.scripts.cleanup_checkpoints
Or with PYTHONPATH:
    PYTHONPATH=backend uv run python supabase/cleanup_checkpoints.py
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add backend directory to Python path so we can import app modules
backend_dir = Path(__file__).parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Note: Database connection string handling is now centralized in app.api.database
# The _build_connection_string() function automatically handles hostname conversion:
# - In Docker: converts localhost -> host.docker.internal
# - On host: converts host.docker.internal -> localhost

import structlog

from app.api.checkpointer import cleanup_checkpointer, initialize_checkpointer
from app.api.database import cleanup_pool, get_pool, initialize_pool
from app.logging import configure_structlog, setup_logging

# Initialize structlog before other imports that might use logging
configure_structlog()

logger = structlog.get_logger(__name__)


async def get_latest_active_threads_by_flow() -> list[dict[str, Any]]:
    """
    Get the latest thread (max 1) for each different flow.
    
    Returns:
        List of thread dictionaries, one per flow, with keys:
        - thread_id (str)
        - user_id (str)
        - title (str | None)
        - flow (str | None)
        - created_at (datetime)
        - last_accessed_at (datetime)
        Empty list if no threads exist
    """
    pool = get_pool()
    
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                # Use DISTINCT ON to get latest thread per flow
                # NULL flows are treated as a separate group
                await cur.execute(
                    """
                    SELECT DISTINCT ON (flow)
                        thread_id, user_id, title, flow, created_at, last_accessed_at
                    FROM public.user_threads
                    ORDER BY flow NULLS LAST, last_accessed_at DESC
                    """
                )
                rows = await cur.fetchall()
                
                threads = []
                for row in rows:
                    thread_id, user_id, title, flow, created_at, last_accessed_at = row
                    threads.append({
                        "thread_id": str(thread_id),
                        "user_id": user_id,
                        "title": title,
                        "flow": flow,
                        "created_at": created_at,
                        "last_accessed_at": last_accessed_at,
                    })
                
                return threads
    except Exception as e:
        logger.error(
            "failed_to_get_latest_threads_by_flow",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        raise


async def get_latest_checkpoint_ids(thread_ids: list[str]) -> dict[str, str | None]:
    """
    Get the latest checkpoint_id for each thread.
    
    The latest checkpoint is the one with no child checkpoints
    (no other checkpoint has this as parent_checkpoint_id).
    
    Args:
        thread_ids: List of thread identifiers
        
    Returns:
        Dictionary mapping thread_id -> checkpoint_id (or None if no checkpoints exist)
    """
    pool = get_pool()
    result: dict[str, str | None] = {}
    
    if not thread_ids:
        return result
    
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                # Get latest checkpoint for each thread
                # Using a single query with array parameter
                await cur.execute(
                    """
                    SELECT DISTINCT ON (thread_id)
                        thread_id, checkpoint_id
                    FROM public.checkpoints
                    WHERE thread_id = ANY(%s::text[])
                      AND checkpoint_id NOT IN (
                          SELECT parent_checkpoint_id
                          FROM public.checkpoints
                          WHERE thread_id = ANY(%s::text[])
                            AND parent_checkpoint_id IS NOT NULL
                      )
                    ORDER BY thread_id, checkpoint_id DESC
                    """,
                    (thread_ids, thread_ids),
                )
                
                rows = await cur.fetchall()
                for row in rows:
                    thread_id, checkpoint_id = row
                    result[str(thread_id)] = checkpoint_id
                
                # Set None for threads without checkpoints
                for thread_id in thread_ids:
                    if thread_id not in result:
                        result[thread_id] = None
                
                return result
    except Exception as e:
        logger.error(
            "failed_to_get_latest_checkpoints",
            thread_ids=thread_ids,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        raise


async def get_latest_checkpoint_id(thread_id: str) -> str | None:
    """
    Get the latest checkpoint_id for a thread.
    
    The latest checkpoint is the one with no child checkpoints
    (no other checkpoint has this as parent_checkpoint_id).
    
    Args:
        thread_id: Thread identifier
        
    Returns:
        Checkpoint ID string or None if no checkpoints exist
    """
    pool = get_pool()
    
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                # Find checkpoint with no children (leaf node)
                await cur.execute(
                    """
                    SELECT checkpoint_id
                    FROM public.checkpoints
                    WHERE thread_id = %s
                      AND checkpoint_id NOT IN (
                          SELECT parent_checkpoint_id
                          FROM public.checkpoints
                          WHERE thread_id = %s
                            AND parent_checkpoint_id IS NOT NULL
                      )
                    ORDER BY checkpoint_id DESC
                    LIMIT 1
                    """,
                    (thread_id, thread_id),
                )
                row = await cur.fetchone()
                
                if row is None:
                    return None
                
                return row[0]
    except Exception as e:
        logger.error(
            "failed_to_get_latest_checkpoint",
            thread_id=thread_id,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        raise


async def get_deletion_counts(
    kept_thread_ids: list[str],
    kept_checkpoint_ids: dict[str, str | None],
) -> dict[str, int]:
    """
    Get counts of records that will be deleted.
    
    Args:
        kept_thread_ids: List of thread IDs to keep
        kept_checkpoint_ids: Dictionary mapping thread_id -> checkpoint_id (or None)
        
    Returns:
        Dictionary with counts for each table
    """
    pool = get_pool()
    counts: dict[str, int] = {}
    
    if not kept_thread_ids:
        return {
            "user_threads": 0,
            "checkpoints": 0,
            "checkpoint_writes": 0,
            "checkpoint_blobs": 0,
        }
    
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                # Count threads to delete
                await cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM public.user_threads
                    WHERE thread_id != ALL(%s::uuid[])
                    """,
                    (kept_thread_ids,),
                )
                counts["user_threads"] = (await cur.fetchone())[0] or 0
                
                # Count checkpoints to delete
                # Get all checkpoint IDs to keep
                kept_checkpoint_id_list = [
                    cid for cid in kept_checkpoint_ids.values() if cid is not None
                ]
                
                if kept_checkpoint_id_list:
                    await cur.execute(
                        """
                        SELECT COUNT(*)
                        FROM public.checkpoints
                        WHERE thread_id != ALL(%s::text[]) 
                           OR checkpoint_id != ALL(%s::text[])
                        """,
                        (kept_thread_ids, kept_checkpoint_id_list),
                    )
                else:
                    await cur.execute(
                        """
                        SELECT COUNT(*)
                        FROM public.checkpoints
                        WHERE thread_id != ALL(%s::text[])
                        """,
                        (kept_thread_ids,),
                    )
                counts["checkpoints"] = (await cur.fetchone())[0] or 0
                
                # Count checkpoint_writes to delete
                if kept_checkpoint_id_list:
                    await cur.execute(
                        """
                        SELECT COUNT(*)
                        FROM public.checkpoint_writes
                        WHERE thread_id != ALL(%s::text[])
                           OR checkpoint_id != ALL(%s::text[])
                        """,
                        (kept_thread_ids, kept_checkpoint_id_list),
                    )
                else:
                    await cur.execute(
                        """
                        SELECT COUNT(*)
                        FROM public.checkpoint_writes
                        WHERE thread_id != ALL(%s::text[])
                        """,
                        (kept_thread_ids,),
                    )
                counts["checkpoint_writes"] = (await cur.fetchone())[0] or 0
                
                # Count checkpoint_blobs to delete
                # checkpoint_blobs don't have checkpoint_id, so we delete by thread_id
                await cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM public.checkpoint_blobs
                    WHERE thread_id != ALL(%s::text[])
                    """,
                    (kept_thread_ids,),
                )
                counts["checkpoint_blobs"] = (await cur.fetchone())[0] or 0
                
                return counts
    except Exception as e:
        logger.error(
            "failed_to_get_deletion_counts",
            kept_thread_ids=kept_thread_ids,
            kept_checkpoint_ids=kept_checkpoint_ids,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        raise


def display_preview(
    kept_threads: list[dict[str, Any]],
    kept_checkpoint_ids: dict[str, str | None],
    deletion_counts: dict[str, int],
) -> None:
    """
    Display preview of what will be kept and deleted.
    
    Args:
        kept_threads: List of thread information that will be kept (one per flow)
        kept_checkpoint_ids: Dictionary mapping thread_id -> checkpoint_id (or None)
        deletion_counts: Counts of records to be deleted per table
    """
    print("\n" + "=" * 70)
    print("CHECKPOINT CLEANUP PREVIEW")
    print("=" * 70)
    print("\n📌 WILL BE KEPT (latest thread per flow):")
    
    if not kept_threads:
        print("  (no threads to keep)")
    else:
        for i, thread in enumerate(kept_threads, 1):
            print(f"\n  Thread {i}:")
            print(f"    Thread ID:     {thread['thread_id']}")
            print(f"    User ID:       {thread['user_id']}")
            flow = thread.get("flow")
            if flow:
                print(f"    Flow:          {flow}")
            else:
                print(f"    Flow:          (NULL - legacy thread)")
            if thread.get("title"):
                print(f"    Title:         {thread['title']}")
            if thread.get("last_accessed_at"):
                last_accessed = thread["last_accessed_at"]
                if isinstance(last_accessed, datetime):
                    print(f"    Last Accessed: {last_accessed.isoformat()}")
                else:
                    print(f"    Last Accessed: {last_accessed}")
            
            checkpoint_id = kept_checkpoint_ids.get(thread['thread_id'])
            if checkpoint_id:
                print(f"    Checkpoint ID: {checkpoint_id}")
            else:
                print(f"    Checkpoint ID: (none - thread has no checkpoints)")
    
    print("\n🗑️  WILL BE DELETED:")
    print(f"  user_threads:        {deletion_counts['user_threads']:,} threads")
    print(f"  checkpoints:         {deletion_counts['checkpoints']:,} checkpoints")
    print(f"  checkpoint_writes:   {deletion_counts['checkpoint_writes']:,} writes")
    print(f"  checkpoint_blobs:    {deletion_counts['checkpoint_blobs']:,} blobs")
    
    total_to_delete = sum(deletion_counts.values())
    print(f"\n  Total records to delete: {total_to_delete:,}")
    print("=" * 70 + "\n")


def ask_confirmation() -> bool:
    """
    Ask user for confirmation to proceed.
    
    Returns:
        True if user confirms, False otherwise
    """
    while True:
        response = input("Proceed with cleanup? (yes/no): ").strip().lower()
        if response in ("yes", "y"):
            return True
        elif response in ("no", "n"):
            return False
        else:
            print("Please enter 'yes' or 'no'")


async def delete_checkpoints(
    kept_thread_ids: list[str],
    kept_checkpoint_ids: dict[str, str | None],
) -> dict[str, int]:
    """
    Delete all checkpoints and threads except the kept ones.
    
    Args:
        kept_thread_ids: List of thread IDs to keep
        kept_checkpoint_ids: Dictionary mapping thread_id -> checkpoint_id (or None)
        
    Returns:
        Dictionary with actual deletion counts per table
    """
    pool = get_pool()
    deleted_counts: dict[str, int] = {}
    
    if not kept_thread_ids:
        return {
            "user_threads": 0,
            "checkpoints": 0,
            "checkpoint_writes": 0,
            "checkpoint_blobs": 0,
        }
    
    try:
        async with pool.connection() as conn:
            # Use transaction to ensure atomicity
            async with conn.transaction():
                async with conn.cursor() as cur:
                    # Get all checkpoint IDs to keep
                    kept_checkpoint_id_list = [
                        cid for cid in kept_checkpoint_ids.values() if cid is not None
                    ]
                    
                    # Delete checkpoint_writes
                    if kept_checkpoint_id_list:
                        await cur.execute(
                            """
                            DELETE FROM public.checkpoint_writes
                            WHERE thread_id != ALL(%s::text[])
                               OR checkpoint_id != ALL(%s::text[])
                            """,
                            (kept_thread_ids, kept_checkpoint_id_list),
                        )
                    else:
                        await cur.execute(
                            """
                            DELETE FROM public.checkpoint_writes
                            WHERE thread_id != ALL(%s::text[])
                            """,
                            (kept_thread_ids,),
                        )
                    deleted_counts["checkpoint_writes"] = cur.rowcount
                    
                    # Delete checkpoint_blobs (by thread_id only)
                    await cur.execute(
                        """
                        DELETE FROM public.checkpoint_blobs
                        WHERE thread_id != ALL(%s::text[])
                        """,
                        (kept_thread_ids,),
                    )
                    deleted_counts["checkpoint_blobs"] = cur.rowcount
                    
                    # Delete checkpoints
                    if kept_checkpoint_id_list:
                        await cur.execute(
                            """
                            DELETE FROM public.checkpoints
                            WHERE thread_id != ALL(%s::text[])
                               OR checkpoint_id != ALL(%s::text[])
                            """,
                            (kept_thread_ids, kept_checkpoint_id_list),
                        )
                    else:
                        await cur.execute(
                            """
                            DELETE FROM public.checkpoints
                            WHERE thread_id != ALL(%s::text[])
                            """,
                            (kept_thread_ids,),
                        )
                    deleted_counts["checkpoints"] = cur.rowcount
                    
                    # Delete user_threads
                    await cur.execute(
                        """
                        DELETE FROM public.user_threads
                        WHERE thread_id != ALL(%s::uuid[])
                        """,
                        (kept_thread_ids,),
                    )
                    deleted_counts["user_threads"] = cur.rowcount
                    
                    logger.info(
                        "checkpoint_cleanup_completed",
                        kept_thread_ids=kept_thread_ids,
                        kept_checkpoint_ids=kept_checkpoint_ids,
                        deleted_counts=deleted_counts,
                    )
                    
                    return deleted_counts
    except Exception as e:
        logger.error(
            "checkpoint_cleanup_failed",
            kept_thread_ids=kept_thread_ids,
            kept_checkpoint_ids=kept_checkpoint_ids,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        raise


async def main() -> None:
    """Main entry point for the cleanup script."""
    try:
        # Initialize logging
        setup_logging()
        logger.info("checkpoint_cleanup_script_started")
        
        # Initialize database and checkpointer
        logger.info("initializing_database_and_checkpointer")
        await initialize_pool()
        await initialize_checkpointer()
        
        # Get latest active threads (one per flow)
        logger.info("finding_latest_active_threads_by_flow")
        kept_threads = await get_latest_active_threads_by_flow()
        
        if not kept_threads:
            print("\n❌ No threads found in database. Nothing to clean up.\n")
            logger.info("no_threads_found")
            return
        
        kept_thread_ids = [thread["thread_id"] for thread in kept_threads]
        logger.info(
            "latest_threads_found",
            thread_count=len(kept_threads),
            thread_ids=kept_thread_ids,
        )
        
        # Get latest checkpoint for each thread
        logger.info("finding_latest_checkpoints", thread_ids=kept_thread_ids)
        kept_checkpoint_ids = await get_latest_checkpoint_ids(kept_thread_ids)
        
        for thread_id, checkpoint_id in kept_checkpoint_ids.items():
            if checkpoint_id:
                logger.info(
                    "latest_checkpoint_found",
                    thread_id=thread_id,
                    checkpoint_id=checkpoint_id,
                )
            else:
                logger.info(
                    "no_checkpoints_for_thread",
                    thread_id=thread_id,
                )
        
        # Get deletion counts
        logger.info("calculating_deletion_counts")
        deletion_counts = await get_deletion_counts(kept_thread_ids, kept_checkpoint_ids)
        
        # Display preview
        display_preview(kept_threads, kept_checkpoint_ids, deletion_counts)
        
        # Ask for confirmation
        if not ask_confirmation():
            print("\n❌ Cleanup cancelled by user.\n")
            logger.info("cleanup_cancelled_by_user")
            return
        
        # Perform deletion
        print("\n🗑️  Starting cleanup...")
        logger.info("starting_cleanup")
        deleted_counts = await delete_checkpoints(kept_thread_ids, kept_checkpoint_ids)
        
        # Display summary
        print("\n✅ Cleanup completed successfully!")
        print(f"  Deleted {deleted_counts['user_threads']:,} threads")
        print(f"  Deleted {deleted_counts['checkpoints']:,} checkpoints")
        print(f"  Deleted {deleted_counts['checkpoint_writes']:,} checkpoint writes")
        print(f"  Deleted {deleted_counts['checkpoint_blobs']:,} checkpoint blobs")
        print()
        
        logger.info(
            "cleanup_completed_successfully",
            deleted_counts=deleted_counts,
        )
        
    except Exception as e:
        print(f"\n❌ Error during cleanup: {e}\n")
        logger.exception(
            "cleanup_script_failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        sys.exit(1)
    finally:
        # Cleanup resources
        logger.info("cleaning_up_resources")
        await cleanup_checkpointer()
        await cleanup_pool()
        logger.info("cleanup_script_finished")


if __name__ == "__main__":
    asyncio.run(main())
