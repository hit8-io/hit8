"""
Centralized database connection pool management and connection utilities.

Provides shared async connection pool and sync connection helpers for all database operations.
Initialized once at application startup via FastAPI lifespan.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
import psycopg
from psycopg_pool import AsyncConnectionPool

from app.config import settings
from app import constants

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)

# Global variables to hold the shared pool
# Initialized once at application startup via FastAPI lifespan
_pool: AsyncConnectionPool | None = None

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


async def initialize_pool() -> None:
    """
    Initialize the async connection pool.
    
    This should be called once at application startup via FastAPI lifespan.
    The pool is stored in a module-level global variable.
    
    Raises:
        Exception: If pool initialization fails
    """
    global _pool
    
    if _pool is not None:
        logger.warning("connection_pool_already_initialized")
        return
    
    conninfo = _build_connection_string()
    
    logger.info(
        "initializing_connection_pool",
        environment=constants.ENVIRONMENT,
        has_ssl=constants.ENVIRONMENT == "prd",
    )
    
    # Create async connection pool with Supabase-compatible settings
    # Set open=False to prevent automatic opening (deprecated behavior)
    _pool = AsyncConnectionPool(
        conninfo=conninfo,
        max_size=20,
        open=False,  # Explicitly control when pool opens
        kwargs={
            "autocommit": True,  # Recommended for Supabase
            "prepare_threshold": None,  # CRITICAL: Disable prepared statements
        },
    )
    
    # Open the pool explicitly (required for newer psycopg_pool versions)
    await _pool.open()
    
    logger.info(
        "connection_pool_initialized",
        pool_type="AsyncConnectionPool",
        environment=constants.ENVIRONMENT,
    )


async def cleanup_pool() -> None:
    """
    Cleanup the connection pool on application shutdown.
    
    This should be called in the FastAPI lifespan shutdown phase.
    """
    global _pool
    
    if _pool is not None:
        logger.info("closing_connection_pool")
        await _pool.close()
        _pool = None
        logger.info("connection_pool_closed")


def get_pool() -> AsyncConnectionPool:
    """
    Get the async connection pool for database operations.
    
    The pool must be initialized via initialize_pool() 
    at application startup before this function is called.
    
    Returns:
        AsyncConnectionPool: The connection pool instance
        
    Raises:
        RuntimeError: If pool has not been initialized
    """
    global _pool
    
    if _pool is None:
        raise RuntimeError(
            "Connection pool has not been initialized. "
            "Ensure initialize_pool() is called at application startup via FastAPI lifespan."
        )
    
    return _pool


def get_sync_connection() -> psycopg.Connection:
    """
    Get a synchronous database connection with SSL support for production Supabase.
    
    This is used for sync operations (e.g., in tools) that cannot use the async pool.
    Creates a new connection each time - consider using the async pool when possible.
    
    - Dev: No SSL (plain connection)
    - Production: SSL with certificate verification (required)
    
    Returns:
        psycopg.Connection: Database connection
        
    Raises:
        ValueError: If DATABASE_SSL_ROOT_CERT is required but not provided
    """
    conninfo = settings.DATABASE_CONNECTION_STRING
    
    # Production requires SSL with certificate verification
    if constants.ENVIRONMENT == "prd":
        if not settings.DATABASE_SSL_ROOT_CERT:
            raise ValueError(
                "DATABASE_SSL_ROOT_CERT is required in production but not provided"
            )
        
        # Write certificate content to file and get path
        cert_file_path = _get_ssl_cert_file_path()
        
        # Connect with SSL verification
        return psycopg.connect(
            conninfo,
            sslmode="verify-full",
            sslrootcert=cert_file_path,
        )
    
    # Dev: No SSL (local database)
    return psycopg.connect(conninfo)
