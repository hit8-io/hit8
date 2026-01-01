"""
FastAPI middleware and exception handlers.
"""
from __future__ import annotations

import structlog
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from firebase_admin.exceptions import FirebaseError

from app.api.utils import get_cors_headers
from app.config import settings

logger = structlog.get_logger(__name__)


def setup_cors(app: FastAPI) -> None:
    """Setup CORS middleware."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def setup_api_token_middleware(app: FastAPI) -> None:
    """Setup middleware to validate X-Source-Token header."""
    
    @app.middleware("http")
    async def api_token_middleware(request: Request, call_next):
        """Validate X-Source-Token header for all requests except health check."""
        # Skip validation for health check endpoint
        if request.url.path == "/health":
            return await call_next(request)
        
        # Get the source token from header
        source_token = request.headers.get("X-Source-Token")
        
        if not source_token:
            logger.warning(
                "api_token_missing",
                path=request.url.path,
                method=request.method,
            )
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "X-Source-Token header is required"},
                headers=get_cors_headers(request),
            )
        
        # Validate token matches configured secret
        if source_token != settings.api_token:
            logger.warning(
                "api_token_invalid",
                path=request.url.path,
                method=request.method,
            )
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Invalid X-Source-Token"},
                headers=get_cors_headers(request),
            )
        
        # Token is valid, proceed with request
        response = await call_next(request)
        return response


def setup_exception_handlers(app: FastAPI) -> None:
    """Setup exception handlers."""
    
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """Handle HTTP exceptions and ensure CORS headers are included."""
        headers = dict(exc.headers) if exc.headers else {}
        headers.update(get_cors_headers(request))
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=headers,
        )
    
    @app.exception_handler(FirebaseError)
    async def firebase_exception_handler(request: Request, exc: FirebaseError):
        """Handle Firebase errors and ensure CORS headers are included."""
        logger.warning(
            "firebase_authentication_failed",
            error=str(exc),
            path=request.url.path,
            method=request.method,
        )
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Authentication failed"},
            headers=get_cors_headers(request),
        )
    
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Handle all exceptions and ensure CORS headers are included."""
        logger.exception("Unhandled exception", exc_info=exc)
        
        # Determine error message based on exception type
        if isinstance(exc, ValueError):
            detail = str(exc)
        else:
            detail = "Internal server error"
        
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": detail},
            headers=get_cors_headers(request),
        )

