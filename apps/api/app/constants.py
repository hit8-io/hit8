"""
Application constants and configuration.

Doppler Secrets Reference
==========================

- API_TOKEN: API token for authentication
- API_URL: Base URL for the API (e.g., "http://localhost:8000")
- DATABASE_CONNECTION_STRING: PostgreSQL connection string for local development
- DIRECT_DB_CONNECTION_STRING: Direct PostgreSQL connection string to Supabase
- DATABASE_SSL_ROOT_CERT: SSL root certificate for database connections (empty for local)
- SUPABASE_SERVICE_ROLE_KEY: Supabase service role key for admin operations
- GCP_PROJECT: GCP project ID (e.g., "hit8-poc")
- VERTEX_SERVICE_ACCOUNT: JSON service account credentials for Vertex AI
- GOOGLE_CLIENT_ID: Google OAuth client ID
- GOOGLE_CLIENT_SECRET: Google OAuth client secret
- GOOGLE_IDENTITY_PLATFORM_DOMAIN: Firebase identity platform domain
- GOOGLE_IDENTITY_PLATFORM_KEY: Firebase identity platform API key
- LANGFUSE_BASE_URL: Langfuse base URL (e.g., "http://langfuse:3000")
- LANGFUSE_PUBLIC_KEY: Langfuse public API key
- LANGFUSE_SECRET_KEY: Langfuse secret API key
- LANGSMITH_API_KEY: LangSmith API key for observability
- SENTRY_DSN: Sentry DSN for error tracking (empty if not configured)
- OPENAI_API_KEY: OpenAI API key for LLM services
- BRIGHTDATA_API_KEY: BrightData API key for web scraping
- N8N_GOOGLE_CLIENT_ID: Google OAuth client ID for n8n integration
- N8N_GOOGLE_CLIENT_SECRET: Google OAuth client secret for n8n integration
- UPSTASH_REDIS_HOST: Upstash Redis endpoint (stg/prd only)
- UPSTASH_REDIS_PWD: Upstash Redis password (stg/prd only)
"""

from __future__ import annotations

import asyncio
import os
import threading
from typing import Any, Literal

import structlog

logger = structlog.get_logger(__name__)

ENVIRONMENT: Literal["dev", "stg", "prd"] = os.getenv("ENVIRONMENT", "dev")

# Vertex AI Configuration (single constants for all models)
VERTEX_LOCATION: str = "europe-west1"
USE_ALTERNATIVE: bool = True

# Defaults
CONSTANTS: dict[str, Any] = {
    "MAX_RECENT_MESSAGE_PAIRS": 5,
    "MAX_TOOL_RESULT_LENGTH": 15_000,
    "APP_NAME": "Hit8 Chat API",
    "APP_VERSION": "0.6.0",
    "LLM": [
        {
            "MODEL_NAME": "gemini-2.5-pro",
            "PROVIDER": "vertex",
            "LOCATION": VERTEX_LOCATION,
            "USE_ALTERNATIVE": USE_ALTERNATIVE,
            "THINKING_LEVEL": None,
            "TEMPERATURE": 0.3,
        },
        {
            "MODEL_NAME": "gemini-2.5-flash",
            "PROVIDER": "vertex",
            "LOCATION": VERTEX_LOCATION,
            "USE_ALTERNATIVE": USE_ALTERNATIVE,
            "THINKING_LEVEL": None,
            "TEMPERATURE": 0.3,
        },
        {
            "MODEL_NAME": "gemini-3-pro-preview",
            "PROVIDER": "vertex",
            "LOCATION": VERTEX_LOCATION,
            "USE_ALTERNATIVE": USE_ALTERNATIVE,
            "THINKING_LEVEL": None,
            "TEMPERATURE": None,
        },
        {
            "MODEL_NAME": "gemini-3-flash-preview",
            "PROVIDER": "vertex",
            "LOCATION": VERTEX_LOCATION,
            "USE_ALTERNATIVE": USE_ALTERNATIVE,
            "THINKING_LEVEL": None,
            "TEMPERATURE": None,
        },
        {
            "MODEL_NAME": "gemini-2.0-flash-lite-001",
            "PROVIDER": "vertex",
            "LOCATION": VERTEX_LOCATION,
            "USE_ALTERNATIVE": USE_ALTERNATIVE,
            "THINKING_LEVEL": None,
            "TEMPERATURE": 0.3,
        },
    ],
    "CORS_ALLOW_CREDENTIALS": True,
    "ACCOUNT": "hit8",
    "ORG": "opgroeien",
    "PROJECT": "poc",
    "FLOW": "chat",
    "PROMPTS_DIR": "app/prompts",
    "LANGFUSE_ENABLED": False,
    "CACHE_ENABLED": False,  # Disabled by default (dev)
    "CACHE_TTL": 3600,  # 1 hour default TTL
    "LLM_RETRY_STOP_AFTER_ATTEMPT": 10,
    "LLM_RETRY_MAX_INTERVAL": 60,
    "LLM_RETRY_INITIAL_INTERVAL": 1.0,
    "REPORT_MAX_PARALLEL_WORKERS": 1,  # Process 1 chapter at a time (Pro models have strict 5 RPM limit)
    "REPORT_LLM_CONCURRENCY": 1,  # Allow 1 concurrent LLM call for reports (Pro models: 5 RPM requires sequential processing)
    "REPORT_CONSULT_LLM_CONCURRENCY": 2,  # Allow 2 concurrent consult calls (nested chat graphs)
    "ANALYST_AGENT_MAX_ITERATIONS": 30,
    "ANALYST_NODE_TIMEOUT": 120.0,  # Timeout for analyst node execution (seconds)
    "ANALYST_NODE_MAX_RETRIES": 3,  # Maximum number of retries for failed analyst nodes (default: 3 retries = 4 total attempts)
    "GRAPH_RECURSION_LIMIT": 50,  # Maximum number of graph steps to prevent infinite loops (agent -> tool -> agent -> ...)
    "LLM_PROVIDER": [
        {
            "PROVIDER": "vertex",
            "VERTEX_AI_MAX_RETRIES": 6,
        },
        {
            "PROVIDER": "ollama",
            "OLLAMA_KEEP_ALIVE": "0",
            "OLLAMA_BASE_URL": "http://213.173.110.232:36161",
            "OLLAMA_NUM_CTX": 65536,
            "OLLAMA_EDITOR_NODE_MAX_OUTPUT_TOKENS": 16384,
        },
    ],
}

# dev
if ENVIRONMENT == "dev":
    CONSTANTS.update(
        {
            "LOG_LEVEL": "DEBUG",
            "LLM": [
                {
                    "MODEL_NAME": "gemini-2.0-flash-lite-001",
                    "PROVIDER": "vertex",
                    "LOCATION": VERTEX_LOCATION,
                    "USE_ALTERNATIVE": USE_ALTERNATIVE,
                    "THINKING_LEVEL": None,
                    "TEMPERATURE": 0.3,
                },
                # {
                #     "MODEL_NAME": "llama3.1:8b",
                #     "PROVIDER": "ollama",
                #     "LOCATION": None,
                #     "THINKING_LEVEL": None,
                #     "TEMPERATURE": 0.3,
                # },
                {
                    "MODEL_NAME": "gemini-2.5-pro",
                    "PROVIDER": "vertex",
                    "LOCATION": VERTEX_LOCATION,
                    "USE_ALTERNATIVE": USE_ALTERNATIVE,
                    "THINKING_LEVEL": None,
                    "TEMPERATURE": 0.3,
                },
                {
                    "MODEL_NAME": "gemini-2.5-flash",
                    "PROVIDER": "vertex",
                    "LOCATION": VERTEX_LOCATION,
                    "USE_ALTERNATIVE": USE_ALTERNATIVE,
                    "THINKING_LEVEL": None,
                    "TEMPERATURE": 0.3,
                },
                {
                    "MODEL_NAME": "gemini-3-pro-preview",
                    "PROVIDER": "vertex",
                    "LOCATION": VERTEX_LOCATION,
                    "USE_ALTERNATIVE": USE_ALTERNATIVE,
                    "THINKING_LEVEL": None,
                    "TEMPERATURE": None,
                },
                {
                    "MODEL_NAME": "gemini-3-flash-preview",
                    "PROVIDER": "vertex",
                    "LOCATION": VERTEX_LOCATION,
                    "USE_ALTERNATIVE": USE_ALTERNATIVE,
                    "THINKING_LEVEL": None,
                    "TEMPERATURE": None,
                },
            ],
            "LOG_FORMAT": "console",
            "CORS_ALLOW_ORIGINS": [
                "http://localhost:5173",
                "http://127.0.0.1:5173",
            ],
            "MAX_BATCHES": None,
            "MAX_PROCEDURES_DEV": None,
        }
    )

# stg
if ENVIRONMENT == "stg":
    CONSTANTS.update(
        {
            "LOG_LEVEL": "DEBUG",
            "LOG_FORMAT": "json",
            "CACHE_ENABLED": True,
            "CORS_ALLOW_ORIGINS": [
                "https://www.hit8.io",
                "https://hit8.io",
                "https://hit8.pages.dev",
                "https://main-staging.hit8.pages.dev",
                "https://iter8.hit8.io",
            ],
            "LANGFUSE_ENABLED": False,
        }
    )

# prd
if ENVIRONMENT == "prd":
    CONSTANTS.update(
        {
            "LOG_LEVEL": "INFO",
            "LOG_FORMAT": "json",
            "CACHE_ENABLED": True,
            "CORS_ALLOW_ORIGINS": [
                "https://www.hit8.io",
                "https://hit8.io",
                "https://hit8.pages.dev",
                "https://iter8.hit8.io",
            ],
            "LANGFUSE_ENABLED": False,
        }
    )

# ============================================================================
# Flow Control Constants (Module Level)
# ============================================================================
# Centralized flow control constants for concurrency management.
# Rate limiting and token management are now handled by LiteLLM Router.

# Concurrency Control
# Maximum number of concurrent analyst nodes (protects Cloud Run instance RAM/CPU)
# LiteLLM Router handles rate limiting, but Pro models have strict 5 RPM limit
# Flash models: 5M TPM, 60 RPM - can handle 3-5 concurrent requests
# Pro models: 250k TPM, 5 RPM - must use 1 concurrent request to avoid 429 errors
# Router's in-memory rate limiting may not perfectly prevent 429s, so we're conservative
MAX_CONCURRENT_ANALYSTS: int = 1

# Timeout Configuration
# Timeout for analyst node execution (seconds)
# Default: 90s (safe upper bound for complex LLM tasks with CoT)
ANALYST_TIMEOUT_SECONDS: float = 90.0

# Retry Configuration
# Maximum number of retries for failed analyst nodes
# Default: 3 retries = 4 total attempts
# Note: LiteLLM Router handles most retries automatically
ANALYST_MAX_RETRIES: int = 3

# Global Flow Control Instances
# Semaphore for concurrency control
ANALYST_SEMAPHORE: asyncio.Semaphore = asyncio.Semaphore(MAX_CONCURRENT_ANALYSTS)
