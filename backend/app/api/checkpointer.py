"""
Checkpointer management for LangGraph with AsyncPostgresSaver.

Provides a shared async connection pool and AsyncPostgresSaver instance
for persistent checkpoint storage across all graph instances.

Initialized once at application startup via FastAPI lifespan.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver  # type: ignore[import-untyped]
from psycopg_pool import AsyncConnectionPool

from app.config import settings
from app import constants

if TYPE_CHECKING:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver as AsyncPostgresSaverType  # type: ignore[import-untyped]

logger = structlog.get_logger(__name__)

# Global variables to hold the shared pool and checkpointer
# Initialized once at application startup via FastAPI lifespan
pool: AsyncConnectionPool | None = None
checkpointer: AsyncPostgresSaverType | None = None

# Cache SSL certificate file path (written from certificate content)
_ssl_cert_file_path: str | None = None


def _get_ssl_cert_file_path() -> str:
    """
    Write SSL certificate content to a temporary file and return the path.
    
    The certificate content is cached in a file that persists for the lifetime
    of the process. This is necessary because psycopg3 requires a file path
    for SSL certificate verification.
    
    Returns:
        str: Path to the certificate file
        
    Raises:
        ValueError: If DATABASE_SSL_ROOT_CERT is required but not provided
    """
    global _ssl_cert_file_path
    
    if _ssl_cert_file_path is not None and os.path.exists(_ssl_cert_file_path):
        return _ssl_cert_file_path
    
    # Production requires SSL with certificate verification
    if constants.ENVIRONMENT == "prd":
        if not settings.DATABASE_SSL_ROOT_CERT:
            raise ValueError(
                "DATABASE_SSL_ROOT_CERT is required in production but not provided"
            )
        
        # Create certs directory if it doesn't exist (for Docker: /app/certs)
        cert_dir = Path("/app/certs") if os.path.exists("/app/certs") else Path(tempfile.gettempdir()) / "hit8_certs"
        cert_dir.mkdir(parents=True, exist_ok=True)
        
        # Write certificate content to file
        cert_file = cert_dir / "prod-ca-2021.crt"
        cert_file.write_text(settings.DATABASE_SSL_ROOT_CERT, encoding="utf-8")
        
        # Set restrictive permissions (read-only for owner)
        os.chmod(cert_file, 0o600)
        
        _ssl_cert_file_path = str(cert_file)
        logger.info(
            "ssl_cert_file_written",
            cert_file=_ssl_cert_file_path,
            environment=constants.ENVIRONMENT,
        )
        
        return _ssl_cert_file_path
    
    # Dev: No SSL certificate needed
    raise ValueError("SSL certificate file path requested in dev environment (should not happen)")


def _build_connection_string() -> str:
    """
    Build connection string with SSL parameters for production.
    
    Returns:
        str: Connection string with SSL parameters if in production
    """
    conninfo = settings.DATABASE_CONNECTION_STRING
    
    
    # Production requires SSL with certificate verification
    if constants.ENVIRONMENT == "prd":
        cert_file_path = _get_ssl_cert_file_path()
        # Append SSL parameters to connection string
        separator = "&" if "?" in conninfo else "?"
        conninfo = f"{conninfo}{separator}sslmode=verify-full&sslrootcert={cert_file_path}"
    
    return conninfo


async def initialize_checkpointer() -> None:
    """
    Initialize the async connection pool and checkpointer.
    
    This should be called once at application startup via FastAPI lifespan.
    The pool and checkpointer are stored in module-level global variables.
    
    Raises:
        Exception: If pool or checkpointer initialization fails
    """
    global pool, checkpointer
    
    if checkpointer is not None:
        logger.warning("checkpointer_already_initialized")
        return
    
    conninfo = _build_connection_string()
    
    logger.info(
        "initializing_checkpointer",
        environment=constants.ENVIRONMENT,
        has_ssl=constants.ENVIRONMENT == "prd",
    )
    
    # Create async connection pool with Supabase-compatible settings
    # Set open=False to prevent automatic opening (deprecated behavior)
    pool = AsyncConnectionPool(
        conninfo=conninfo,
        max_size=20,
        open=False,  # Explicitly control when pool opens
        kwargs={
            "autocommit": True,  # Recommended for Supabase
            "prepare_threshold": None,  # CRITICAL: Disable prepared statements
        },
    )
    
    # Open the pool explicitly (required for newer psycopg_pool versions)
    await pool.open()
    
    # Initialize checkpointer with the pool
    checkpointer = AsyncPostgresSaver(pool)
    
    logger.info(
        "checkpointer_initialized",
        checkpointer_type="AsyncPostgresSaver",
        environment=constants.ENVIRONMENT,
    )


async def cleanup_checkpointer() -> None:
    """
    Cleanup the connection pool on application shutdown.
    
    This should be called in the FastAPI lifespan shutdown phase.
    """
    global pool, checkpointer
    
    if pool is not None:
        logger.info("closing_checkpointer_pool")
        await pool.close()
        pool = None
        checkpointer = None
        logger.info("checkpointer_pool_closed")


def get_checkpointer() -> AsyncPostgresSaverType:
    """
    Get the AsyncPostgresSaver checkpointer instance.
    
    The checkpointer must be initialized via initialize_checkpointer() 
    at application startup before this function is called.
    
    Returns:
        AsyncPostgresSaver: The checkpointer instance
        
    Raises:
        RuntimeError: If checkpointer has not been initialized
    """
    global checkpointer
    
    if checkpointer is None:
        raise RuntimeError(
            "Checkpointer has not been initialized. "
            "Ensure initialize_checkpointer() is called at application startup via FastAPI lifespan."
        )
    
    return checkpointer


async def setup_checkpointer() -> None:
    """
    Run checkpointer.setup() to create database tables.
    
    This should be called manually via the setup script before using the checkpointer
    in production. The tables are created once and persist across application restarts.
    
    Raises:
        Exception: If setup fails
    """
    # Initialize checkpointer if not already initialized
    if checkpointer is None:
        await initialize_checkpointer()
    
    logger.info("running_checkpointer_setup")
    
    try:
        await checkpointer.setup()
        logger.info("checkpointer_setup_completed")
    except Exception as e:
        logger.error(
            "checkpointer_setup_failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        raise
