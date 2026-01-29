#!/usr/bin/env python3
"""
Cleanup script for LangGraph checkpoints (Final Fix).

Fixes:
1. Timestamp Parsing: Handles both ISO strings and Unix Epochs in JSON.
2. Schema Correction: correctly links 'checkpoint_blobs' to 'checkpoints' via JSONB channel_versions
   (instead of the non-existent 'version' column in 'checkpoint_writes').
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

# Add scripts directory to path for common module
scripts_path = Path(__file__).parent
sys.path.insert(0, str(scripts_path))

import structlog
from app.logging import configure_structlog, setup_logging
from common import get_db_connection

configure_structlog()
setup_logging()
logger = structlog.get_logger(__name__)

def cleanup_checkpoints() -> None:
    start_time = time.time()
    
    # -------------------------------------------------------------------------
    # SQL COMPONENTS
    # -------------------------------------------------------------------------
    
    # 1. Robust Timestamp Parser (Handles Float/Int and ISO String)
    TIMESTAMP_PARSER = """
    CASE 
        WHEN COALESCE(metadata->>'ts', checkpoint->>'ts') IS NULL THEN NOW()
        WHEN COALESCE(metadata->>'ts', checkpoint->>'ts') ~ '^\\d+(\\.\\d+)?$' 
            THEN to_timestamp((COALESCE(metadata->>'ts', checkpoint->>'ts'))::double precision)
        ELSE (COALESCE(metadata->>'ts', checkpoint->>'ts'))::timestamptz
    END
    """

    # 2. Cleanup Inactive Threads (> 1 day old)
    DELETE_WRITES_INACTIVE_SQL = f"""
        DELETE FROM hit8.checkpoint_writes 
        WHERE thread_id IN (
            SELECT thread_id 
            FROM hit8.checkpoints 
            GROUP BY thread_id 
            HAVING MAX({TIMESTAMP_PARSER}) < (NOW() - INTERVAL '1 day')
        );
    """
    
    DELETE_THREADS_INACTIVE_SQL = f"""
        DELETE FROM hit8.checkpoints
        WHERE thread_id IN (
            SELECT thread_id 
            FROM hit8.checkpoints 
            GROUP BY thread_id 
            HAVING MAX({TIMESTAMP_PARSER}) < (NOW() - INTERVAL '1 day')
        );
    """
    
    # Cleanup user_threads for inactive threads (thread_id is UUID in user_threads, TEXT in checkpoints)
    DELETE_USER_THREADS_INACTIVE_SQL = f"""
        DELETE FROM hit8.user_threads
        WHERE thread_id::text IN (
            SELECT thread_id 
            FROM hit8.checkpoints 
            GROUP BY thread_id 
            HAVING MAX({TIMESTAMP_PARSER}) < (NOW() - INTERVAL '1 day')
        );
    """
    
    # Cleanup orphaned user_threads (threads with no checkpoints)
    DELETE_USER_THREADS_ORPHANED_SQL = """
        DELETE FROM hit8.user_threads
        WHERE thread_id::text NOT IN (
            SELECT DISTINCT thread_id FROM hit8.checkpoints
        );
    """

    # 3. Prune History (Keep Top 3 per thread)
    PRUNE_WRITES_HISTORY_SQL = """
        WITH ranked_checkpoints AS (
            SELECT thread_id, checkpoint_id, checkpoint_ns,
            ROW_NUMBER() OVER (PARTITION BY thread_id ORDER BY checkpoint_id DESC) as rn
            FROM hit8.checkpoints
        )
        DELETE FROM hit8.checkpoint_writes
        WHERE (thread_id, checkpoint_id) IN (
            SELECT thread_id, checkpoint_id FROM ranked_checkpoints WHERE rn > 3
        );
    """

    PRUNE_CHECKPOINTS_HISTORY_SQL = """
        WITH ranked_checkpoints AS (
            SELECT thread_id, checkpoint_id,
            ROW_NUMBER() OVER (PARTITION BY thread_id ORDER BY checkpoint_id DESC) as rn
            FROM hit8.checkpoints
        )
        DELETE FROM hit8.checkpoints
        WHERE (thread_id, checkpoint_id) IN (
            SELECT thread_id, checkpoint_id FROM ranked_checkpoints WHERE rn > 3
        );
    """

    # 4. Clean Orphaned Blobs (CORRECTED)
    # Checks if the blob is referenced in ANY remaining checkpoint's 'channel_versions' map.
    CLEAN_ORPHAN_BLOBS_SQL = """
        DELETE FROM hit8.checkpoint_blobs b
        WHERE NOT EXISTS (
            SELECT 1
            FROM hit8.checkpoints c,
                 jsonb_each_text(c.checkpoint -> 'channel_versions') AS cv(channel, version)
            WHERE c.thread_id = b.thread_id
              AND c.checkpoint_ns = b.checkpoint_ns
              AND cv.channel = b.channel
              AND cv.version = b.version
        );
    """

    with get_db_connection(autocommit=True) as conn:
        with conn.cursor() as cursor:
            logger.info("cleanup_started")

            # Step 1: Delete Inactive Threads
            # Note: Deleting writes first to be safe (though Cascade might handle it)
            logger.info("step_1_cleaning_inactive_threads")
            cursor.execute(DELETE_WRITES_INACTIVE_SQL)
            writes_del = cursor.rowcount
            cursor.execute(DELETE_THREADS_INACTIVE_SQL)
            threads_del = cursor.rowcount
            cursor.execute(DELETE_USER_THREADS_INACTIVE_SQL)
            user_threads_inactive_del = cursor.rowcount
            logger.info("inactive_cleaned", threads_deleted=threads_del, writes_deleted=writes_del, user_threads_deleted=user_threads_inactive_del)

            # Step 2: Prune History (Keep 3)
            logger.info("step_2_pruning_history")
            cursor.execute(PRUNE_WRITES_HISTORY_SQL)
            cursor.execute(PRUNE_CHECKPOINTS_HISTORY_SQL)
            pruned = cursor.rowcount
            logger.info("history_pruned", checkpoints_deleted=pruned)

            # Step 3: Clean Orphaned Blobs
            logger.info("step_3_cleaning_orphans")
            cursor.execute(CLEAN_ORPHAN_BLOBS_SQL)
            blobs = cursor.rowcount
            logger.info("orphans_cleaned", blobs_deleted=blobs)
            
            # Step 4: Clean Orphaned User Threads (threads with no checkpoints)
            logger.info("step_4_cleaning_orphaned_user_threads")
            cursor.execute(DELETE_USER_THREADS_ORPHANED_SQL)
            user_threads_orphaned_del = cursor.rowcount
            logger.info("orphaned_user_threads_cleaned", user_threads_deleted=user_threads_orphaned_del)

    logger.info("cleanup_completed", duration=time.time() - start_time)

def main() -> int:
    try:
        cleanup_checkpoints()
        return 0
    except Exception as e:
        logger.error("cleanup_failed", error=str(e))
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
