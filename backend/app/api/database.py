"""
Centralized database connection pool management and connection utilities.

Provides shared async connection pool and sync connection helpers for all database operations.
Initialized once at application startup via FastAPI lifespan.
"""
from __future__ import annotations

import os
import re
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


def _is_running_in_docker() -> bool:
    """
    Detect if we're running inside a Docker container.
    
    Returns:
        bool: True if running in Docker, False otherwise
    """
    # Check for /.dockerenv file (Docker creates this)
    if os.path.exists("/.dockerenv"):
        return True
    
    # Check /proc/1/cgroup for Docker indicators
    if os.path.exists("/proc/1/cgroup"):
        try:
            with open("/proc/1/cgroup", encoding="utf-8") as f:
                content = f.read()
                if "docker" in content or "containerd" in content:
                    return True
        except Exception:
            pass
    
    return False


def _build_connection_string() -> str:
    """
    Build connection string with SSL parameters for production.
    
    In development, automatically handles hostname conversion:
    - If running in Docker and connection string uses localhost, converts to host.docker.internal
    - If running on host and connection string uses host.docker.internal, converts to localhost
    
    For production, removes any existing SSL parameters from the connection string
    and adds correct ones using the certificate from DATABASE_SSL_ROOT_CERT.
    
    Returns:
        str: Connection string with SSL parameters if in production
    """
    conninfo = settings.DATABASE_CONNECTION_STRING
    
    # In dev, handle hostname conversion for Docker compatibility
    if constants.ENVIRONMENT == "dev":
        is_in_docker = _is_running_in_docker()
        
        if is_in_docker and "localhost" in conninfo:
            # Running in Docker, convert localhost to host.docker.internal
            conninfo = conninfo.replace("localhost", "host.docker.internal")
            logger.debug(
                "connection_string_updated_for_docker",
                original_host="localhost",
                new_host="host.docker.internal",
            )
        elif not is_in_docker and "host.docker.internal" in conninfo:
            # Running on host, convert host.docker.internal to localhost
            conninfo = conninfo.replace("host.docker.internal", "localhost")
            logger.debug(
                "connection_string_updated_for_host",
                original_host="host.docker.internal",
                new_host="localhost",
            )
    
    # Production requires SSL with certificate verification
    if constants.ENVIRONMENT == "prd":
        # Remove any existing SSL parameters (they might point to non-existent files)
        conninfo = re.sub(r'[&?]sslmode=[^&]*', '', conninfo)
        conninfo = re.sub(r'[&?]sslrootcert=[^&]*', '', conninfo)
        # Clean up any double separators
        conninfo = re.sub(r'[?&]+', '&', conninfo)
        conninfo = conninfo.rstrip('&?')
        
        # Get certificate file path (reads from DATABASE_SSL_ROOT_CERT and writes to temp file)
        cert_file_path = _get_ssl_cert_file_path()
        
        # Append SSL parameters using the certificate from DATABASE_SSL_ROOT_CERT
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
    try:
        await _pool.open()
    except Exception as e:
        _pool = None
        logger.error(
            "database_connection_failed",
            error=str(e),
            error_type=type(e).__name__,
            environment=constants.ENVIRONMENT,
        )
        raise RuntimeError(
            "Database connection failed at startup. Check DATABASE_CONNECTION_STRING, "
            "network/firewall, and SSL (DATABASE_SSL_ROOT_CERT for prd, sslmode=require for stg). "
            "See logs for the underlying error."
        ) from e

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
    
    Uses the same connection string building logic as async pool to ensure
    consistent hostname handling (localhost <-> host.docker.internal conversion).
    
    - Dev: No SSL (plain connection), automatically handles hostname conversion
    - Production: SSL with certificate verification (required)
    
    Returns:
        psycopg.Connection: Database connection
        
    Raises:
        ValueError: If DATABASE_SSL_ROOT_CERT is required but not provided
    """
    # Use the same connection string building logic as async pool
    # This ensures consistent hostname handling
    conninfo = _build_connection_string()
    
    # Production requires SSL with certificate verification
    if constants.ENVIRONMENT == "prd":
        if not settings.DATABASE_SSL_ROOT_CERT:
            raise ValueError(
                "DATABASE_SSL_ROOT_CERT is required in production but not provided"
            )
        
        # Extract SSL parameters from connection string if present
        # Otherwise use certificate file path
        if "sslmode=" in conninfo and "sslrootcert=" in conninfo:
            # SSL params already in connection string, use as-is
            return psycopg.connect(conninfo)
        else:
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
