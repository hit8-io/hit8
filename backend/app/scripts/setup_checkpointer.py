"""
Setup script for LangGraph checkpointer database tables.

This script initializes the AsyncPostgresSaver checkpointer and creates
the necessary database tables for checkpoint persistence.

Usage:
    uv run python -m app.scripts.setup_checkpointer
"""
from __future__ import annotations

import asyncio
import sys

import structlog

from app.api.checkpointer import setup_checkpointer
from app.logging import configure_structlog

# Initialize structlog before other imports that might use logging
configure_structlog()

logger = structlog.get_logger(__name__)


async def main() -> None:
    """Run checkpointer setup."""
    try:
        logger.info("starting_checkpointer_setup")
        await setup_checkpointer()
        logger.info("checkpointer_setup_successful")
        print("✓ Checkpointer setup completed successfully")
    except Exception as e:
        logger.error(
            "checkpointer_setup_failed",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        print(f"✗ Checkpointer setup failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
