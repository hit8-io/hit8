"""
Debug endpoint for config and connectivity checks (DB, Redis).

Use for troubleshooting container networking and config in stg/prd.
No secrets are returned; connection strings are sanitized.
See .cursor/docs/debugging-redis-vpc.md for strategy when Redis is in a VPC.
"""
from __future__ import annotations

import os
import re
import time
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

    # Redis (same timeouts as app: 30s for Scaleway VPC, 3s otherwise)
    result["connectivity"]["redis"] = await _redis_connectivity()

    return result


def _redis_socket_timeout() -> int:
    """Match app/LiteLLM: 30s for Scaleway VPC, 3s otherwise."""
    provider = os.getenv("BACKEND_PROVIDER", "").strip().lower()
    return 30 if provider == "scw" else 3


async def _redis_connectivity() -> dict[str, Any]:
    """Return redis connectivity status, ping_ms, set/get test, and on error details."""
    if not settings.REDIS_HOST:
        return {"status": "skipped", "reason": "REDIS_HOST not set"}
    timeout = _redis_socket_timeout()
    use_tls = _redis_use_tls()
    try:
        import redis.asyncio as redis

        client = redis.Redis(
            host=settings.REDIS_HOST,
            port=6379,
            password=settings.REDIS_PWD or None,
            ssl=use_tls,
            socket_connect_timeout=timeout,
            socket_timeout=timeout,
            decode_responses=True,
        )
        t0 = time.perf_counter()
        await client.ping()
        ping_ms = round((time.perf_counter() - t0) * 1000)
        set_get_ok, set_get_ms, set_get_error = await _redis_set_get_test(client)
        await client.aclose()
        out: dict[str, Any] = {"status": "ok", "ssl": use_tls, "ping_ms": ping_ms, "set_get_ok": set_get_ok}
        if set_get_ms is not None:
            out["set_get_ms"] = set_get_ms
        if set_get_error is not None:
            out["set_get_error"] = set_get_error
        return out
    except Exception as e:
        return {
            "status": "error",
            "error_type": type(e).__name__,
            "error": str(e)[:200],
            "ssl": use_tls,
        }


async def _redis_set_get_test(client: Any) -> tuple[bool, int | None, str | None]:
    """Set a test key, get it back, delete it. Returns (ok, ms, error)."""
    try:
        t0 = time.perf_counter()
        value = str(time.perf_counter())
        await client.set(_DEBUG_REDIS_KEY, value, ex=_DEBUG_REDIS_TTL_SEC)
        got = await client.get(_DEBUG_REDIS_KEY)
        await client.delete(_DEBUG_REDIS_KEY)
        ms = round((time.perf_counter() - t0) * 1000)
        return (got == value, ms, None if got == value else f"value mismatch: set {value!r} got {got!r}")
    except Exception as e:
        return (False, None, f"{type(e).__name__}: {str(e)[:150]}")


_DEBUG_REDIS_KEY = "hit8:debug:set_get_test"
_DEBUG_REDIS_TTL_SEC = 10


@router.get("/debug/redis")
async def debug_redis() -> dict[str, Any]:
    """
    Redis ping, set/get round-trip (like LiteLLM health check), and basic INFO.

    Use when you need more than connectivity: e.g. latency trends, memory, read/write check.
    """
    if not settings.REDIS_HOST:
        return {"status": "skipped", "reason": "REDIS_HOST not set"}
    timeout = _redis_socket_timeout()
    use_tls = _redis_use_tls()
    try:
        import redis.asyncio as redis

        client = redis.Redis(
            host=settings.REDIS_HOST,
            port=6379,
            password=settings.REDIS_PWD or None,
            ssl=use_tls,
            socket_connect_timeout=timeout,
            socket_timeout=timeout,
            decode_responses=True,
        )
        t0 = time.perf_counter()
        await client.ping()
        ping_ms = round((time.perf_counter() - t0) * 1000)
        set_get_ok, set_get_ms, set_get_error = await _redis_set_get_test(client)
        info = await client.info()
        await client.aclose()
        # INFO can be flat or sectioned (Redis 6+); read from either
        def _get(key: str) -> Any:
            v = info.get(key)
            if v is not None:
                return v
            for section in ("server", "memory", "clients"):
                sub = info.get(section)
                if isinstance(sub, dict) and sub.get(key) is not None:
                    return sub.get(key)
            return None
        out: dict[str, Any] = {
            "status": "ok",
            "ping_ms": ping_ms,
            "set_get_ok": set_get_ok,
            "set_get_ms": set_get_ms,
            "ssl": use_tls,
            "redis_version": _get("redis_version"),
            "connected_clients": _get("connected_clients"),
            "used_memory_human": _get("used_memory_human"),
            "maxmemory_human": _get("maxmemory_human") or "0",
        }
        if set_get_error is not None:
            out["set_get_error"] = set_get_error
        return out
    except Exception as e:
        return {
            "status": "error",
            "error_type": type(e).__name__,
            "error": str(e)[:200],
            "ssl": use_tls,
        }
