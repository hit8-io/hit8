"""
Debug endpoint for config and connectivity checks (DB, Redis).

Use for troubleshooting container networking and config in stg/prd.
No secrets are returned; connection strings are sanitized.
"""
from __future__ import annotations

import os
import re
from typing import Any

from fastapi import APIRouter

from app import constants
from app.config import settings

router = APIRouter()


def _truncate(s: str, max_len: int) -> str:
    return s[:max_len] + "..." if len(s) > max_len else s


def _sanitize_connection_string(raw: str) -> str:
    """Return a safe representation of the DB connection string (no password)."""
    if not raw or not raw.strip():
        return "(empty)"
    s = raw.strip()
    if s.startswith("postgresql://") or s.startswith("postgres://"):
        # Replace password (between : and @) with ***
        s = re.sub(r"://([^:]*):([^@]*)@", r"://\1:***@", s, count=1)
    return s[:80] + ("..." if len(s) > 80 else "")


def _redis_use_tls() -> bool:
    """Match LiteLLM logic: TLS for Upstash or when not Scaleway."""
    host = (settings.REDIS_HOST or "").strip().lower()
    provider = os.getenv("BACKEND_PROVIDER", "").strip().lower()
    return "upstash" in host or provider != "scw"


@router.get("/debug")
@router.get("/debug/connectivity")
async def debug_connectivity() -> dict[str, Any]:
    """
    Check config and connectivity to DB and Redis.

    Returns sanitized config (no secrets) and per-service status with error messages.
    """
    result: dict[str, Any] = {
        "config": {
            "environment": constants.ENVIRONMENT,
            "backend_provider": os.getenv("BACKEND_PROVIDER", ""),
            "database_connection_string": _sanitize_connection_string(
                getattr(settings, "DATABASE_CONNECTION_STRING", "") or ""
            ),
            "redis_host_set": bool(settings.REDIS_HOST),
            "redis_host_preview": _truncate(settings.REDIS_HOST or "(not set)", 28),
            "cache_enabled": settings.CACHE_ENABLED,
        },
        "connectivity": {},
    }

    # Database
    try:
        from app.api.database import get_pool

        pool = get_pool()
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")
                await cur.fetchone()
        result["connectivity"]["database"] = {"status": "ok"}
    except Exception as e:
        result["connectivity"]["database"] = {
            "status": "error",
            "error_type": type(e).__name__,
            "error": str(e)[:200],
        }

    # Redis
    if not settings.REDIS_HOST:
        result["connectivity"]["redis"] = {"status": "skipped", "reason": "REDIS_HOST not set"}
    else:
        try:
            import redis.asyncio as redis

            use_tls = _redis_use_tls()
            client = redis.Redis(
                host=settings.REDIS_HOST,
                port=6379,
                password=settings.REDIS_PWD or None,
                ssl=use_tls,
                socket_connect_timeout=3,
                socket_timeout=3,
            )
            await client.ping()
            await client.aclose()
            result["connectivity"]["redis"] = {"status": "ok", "ssl": use_tls}
        except Exception as e:
            result["connectivity"]["redis"] = {
                "status": "error",
                "error_type": type(e).__name__,
                "error": str(e)[:200],
                "ssl": _redis_use_tls(),
            }

    return result
