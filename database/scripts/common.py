"""
Common utilities for database scripts.

Provides shared database connection logic used across all scripts in this directory.
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

import psycopg

from app.config import settings
from app import constants

logger = None  # Will be set by scripts that import this


def _is_running_in_docker() -> bool:
    """Detect if we're running inside a Docker container.
    
    Returns:
        True if running in Docker, False otherwise
    """
    if os.path.exists("/.dockerenv"):
        return True
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
    """Build connection string with SSL parameters for production.
    
    Handles:
    - Dev: Hostname conversion for Docker compatibility (localhost <-> host.docker.internal)
    - Production: SSL certificate verification
    
    Returns:
        Connection string ready for psycopg.connect()
    """
    conninfo = settings.DATABASE_CONNECTION_STRING
    
    # In dev, handle hostname conversion for Docker compatibility
    if constants.ENVIRONMENT == "dev":
        is_in_docker = _is_running_in_docker()
        
        if is_in_docker and "localhost" in conninfo:
            conninfo = conninfo.replace("localhost", "host.docker.internal")
        elif not is_in_docker and "host.docker.internal" in conninfo:
            conninfo = conninfo.replace("host.docker.internal", "localhost")
    
    # Production requires SSL with certificate verification
    if constants.ENVIRONMENT == "prd":
        # Remove any existing SSL parameters
        conninfo = re.sub(r'[&?]sslmode=[^&]*', '', conninfo)
        conninfo = re.sub(r'[&?]sslrootcert=[^&]*', '', conninfo)
        conninfo = re.sub(r'[?&]+', '&', conninfo)
        conninfo = conninfo.rstrip('&?')
        
        # Get certificate file path
        cert_dir = Path(tempfile.gettempdir()) / "hit8_certs"
        cert_dir.mkdir(parents=True, exist_ok=True)
        cert_file = cert_dir / "prod-ca-2021.crt"
        cert_file.write_text(settings.DATABASE_SSL_ROOT_CERT, encoding="utf-8")
        os.chmod(cert_file, 0o600)
        
        separator = "&" if "?" in conninfo else "?"
        conninfo = f"{conninfo}{separator}sslmode=verify-full&sslrootcert={cert_file}"
    
    return conninfo


def get_db_connection(autocommit: bool = False, register_vector_type: bool = False) -> psycopg.Connection:
    """Get database connection using the same logic as the app.
    
    Args:
        autocommit: If True, connection uses autocommit mode. If False, uses explicit transactions.
        register_vector_type: If True, registers pgvector type adapter for automatic conversion.
        
    Returns:
        psycopg.Connection: Database connection
        
    Raises:
        ValueError: If DATABASE_SSL_ROOT_CERT is required but not provided (production)
    """
    conninfo = _build_connection_string()
    
    # Production requires SSL with certificate verification
    if constants.ENVIRONMENT == "prd":
        if not settings.DATABASE_SSL_ROOT_CERT:
            raise ValueError(
                "DATABASE_SSL_ROOT_CERT is required in production but not provided"
            )
        
        # Extract SSL parameters from connection string if present
        if "sslmode=" in conninfo and "sslrootcert=" in conninfo:
            conn = psycopg.connect(conninfo, autocommit=autocommit)
        else:
            # Fallback: extract cert path from connection string or create it
            cert_dir = Path(tempfile.gettempdir()) / "hit8_certs"
            cert_dir.mkdir(parents=True, exist_ok=True)
            cert_file = cert_dir / "prod-ca-2021.crt"
            cert_file.write_text(settings.DATABASE_SSL_ROOT_CERT, encoding="utf-8")
            os.chmod(cert_file, 0o600)
            
            conn = psycopg.connect(
                conninfo,
                sslmode="verify-full",
                sslrootcert=str(cert_file),
                autocommit=autocommit,
            )
    else:
        # Dev: No SSL (local database)
        conn = psycopg.connect(conninfo, autocommit=autocommit)
    
    # Register vector type if requested
    if register_vector_type:
        try:
            from pgvector.psycopg import register_vector
            register_vector(conn)
        except ImportError:
            # pgvector not available, skip registration
            pass
    
    return conn
