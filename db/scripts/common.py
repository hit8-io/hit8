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


def _get_ssl_cert_file_path() -> str:
    """Write SSL certificate content to a temp file and return the path. Only used in prd when cert is set."""
    if not settings.DATABASE_SSL_ROOT_CERT:
        raise ValueError("DATABASE_SSL_ROOT_CERT must be set when using verify-full (cert path requested)")
    cert_dir = Path("/app/certs") if os.path.exists("/app/certs") else Path(tempfile.gettempdir()) / "hit8_certs"
    cert_dir.mkdir(parents=True, exist_ok=True)
    cert_file = cert_dir / "prod-ca-2021.crt"
    cert_file.write_text(settings.DATABASE_SSL_ROOT_CERT, encoding="utf-8")
    os.chmod(cert_file, 0o600)
    return str(cert_file)


def _build_connection_string() -> str:
    """Build connection string. Mirrors backend/app/api/database.py.

    - Dev: Hostname conversion for Docker (localhost <-> host.docker.internal).
    - Prd: When DATABASE_SSL_ROOT_CERT is set, use cert (even if ENVIRONMENT not set by Doppler).
    - Stg: SSL with system CA so libpq does not look for ~/.postgresql/root.crt.
    """
    conninfo = settings.DATABASE_CONNECTION_STRING

    # Dev: hostname conversion when running against localhost (same as app)
    if constants.ENVIRONMENT == "dev" and ("localhost" in conninfo or "host.docker.internal" in conninfo):
        is_in_docker = _is_running_in_docker()
        if is_in_docker and "localhost" in conninfo:
            conninfo = conninfo.replace("localhost", "host.docker.internal")
        elif not is_in_docker and "host.docker.internal" in conninfo:
            conninfo = conninfo.replace("host.docker.internal", "localhost")
        return conninfo

    # Prd: cert when DATABASE_SSL_ROOT_CERT is set (GCP); else sslmode=require (Scaleway, no cert)
    if constants.ENVIRONMENT == "prd":
        conninfo = re.sub(r'[&?]sslmode=[^&]*', '', conninfo)
        conninfo = re.sub(r'[&?]sslrootcert=[^&]*', '', conninfo)
        conninfo = re.sub(r'[?&]+', '&', conninfo)
        conninfo = conninfo.rstrip('&?')
        separator = "&" if "?" in conninfo else "?"
        if settings.DATABASE_SSL_ROOT_CERT:
            cert_file_path = _get_ssl_cert_file_path()
            return f"{conninfo}{separator}sslmode=verify-full&sslrootcert={cert_file_path}"
        return f"{conninfo}{separator}sslmode=require"

    # Stg: SSL, no custom cert — use system CA
    if constants.ENVIRONMENT == "stg":
        conninfo = re.sub(r'[&?]sslmode=[^&]*', '', conninfo)
        conninfo = re.sub(r'[&?]sslrootcert=[^&]*', '', conninfo)
        conninfo = re.sub(r'[?&]+', '&', conninfo)
        conninfo = conninfo.rstrip('&?')
        sep = "&" if "?" in conninfo else "?"
        return f"{conninfo}{sep}sslmode=require&sslrootcert=system"

    return conninfo


def get_db_connection(autocommit: bool = False, register_vector_type: bool = False) -> psycopg.Connection:
    """Get database connection. Mirrors backend/app/api/database.py get_sync_connection().

    - Dev: No SSL (local database).
    - Stg: SSL with system CA (conninfo from _build_connection_string).
    - Prd: SSL with certificate (DATABASE_SSL_ROOT_CERT only).
    """
    conninfo = _build_connection_string()

    # Dev / Stg / Prd: conninfo from _build_connection_string already has correct SSL params
    conn = psycopg.connect(conninfo, autocommit=autocommit)

    if register_vector_type:
        try:
            from pgvector.psycopg import register_vector
            register_vector(conn)
        except ImportError:
            pass

    return conn
