"""
FastAPI middleware and exception handlers.
"""
from __future__ import annotations

import structlog
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from firebase_admin.exceptions import FirebaseError

# Health check path (only used in this module)
HEALTH_CHECK_PATH = "/health"
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


def _create_error_response(
    request: Request,
    status_code: int,
    detail: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Create an error response with CORS headers.
    
    Args:
        request: FastAPI request object
        status_code: HTTP status code
        detail: Error detail message
        headers: Additional headers to include
        
    Returns:
        JSONResponse with error details and CORS headers
    """
    response_headers = get_cors_headers(request)
    if headers:
        response_headers.update(headers)
    
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail},
        headers=response_headers,
    )


def setup_api_token_middleware(app: FastAPI) -> None:
    """Setup middleware to validate X-Source-Token header."""
    
    @app.middleware("http")
    async def verify_api_token(request: Request, call_next):
        """Validate X-Source-Token header for all requests except health check and OPTIONS."""
        # Skip validation for preflight requests (let CORSMiddleware handle)
        if request.method == "OPTIONS":
            return await call_next(request)
        
        # Skip validation for health check endpoint
        if request.url.path == HEALTH_CHECK_PATH:
            return await call_next(request)
        
        # Validate token for all other requests
        token = request.headers.get("X-Source-Token")
        if token != settings.api_token:
            logger.warning(
                "api_token_invalid",
                path=request.url.path,
                method=request.method,
            )
            return _create_error_response(
                request,
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Unauthorized",
            )
        
        return await call_next(request)


def setup_exception_handlers(app: FastAPI) -> None:
    """Setup exception handlers."""
    
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """Handle HTTP exceptions and ensure CORS headers are included."""
        headers = dict(exc.headers) if exc.headers else None
        return _create_error_response(
            request,
            status_code=exc.status_code,
            detail=exc.detail,
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
        return _create_error_response(
            request,
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
        )
    
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Handle all exceptions and ensure CORS headers are included."""
        logger.exception("unhandled_exception", exc_info=exc)
        
        # Determine error message based on exception type
        detail = str(exc) if isinstance(exc, ValueError) else "Internal server error"
        
        return _create_error_response(
            request,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
        )

