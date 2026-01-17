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
"""

from __future__ import annotations

import os
from typing import Any, Literal

ENVIRONMENT: Literal["dev", "prd"] = os.getenv("ENVIRONMENT", "dev")

# Defaults
CONSTANTS: dict[str, Any] = {
    "MAX_RECENT_MESSAGE_PAIRS": 5,
    "MAX_TOOL_RESULT_LENGTH": 15_000,
    "APP_NAME": "Hit8 Chat API",
    "APP_VERSION": "0.3.0",
    "LLM_PROVIDER": "vertex",
    # "LLM_MODEL_NAME": "gemini-3-pro-preview",
    "LLM_MODEL_NAME": "gemini-2.0-flash-lite-001",
    "TOOL_LLM_MODEL": "gemini-3-flash-preview",
    "VERTEX_AI_LOCATION": "global",
    "LLM_THINKING_LEVEL": None,
    "TOOL_LLM_THINKING_LEVEL": None,
    "LLM_TEMPERATURE": None,
    "TOOL_LLM_TEMPERATURE": None,
    "LLM_PROVIDER": "vertex",
    "CORS_ALLOW_CREDENTIALS": True,
    "ACCOUNT": "hit8",
    "ORG": "opgroeien",
    "PROJECT": "poc",
    "FLOW": "chat",
    "PROMPTS_DIR": "app/prompts",
    "LANGFUSE_ENABLED": True,
}

# dev
if ENVIRONMENT == "dev":
    CONSTANTS.update({
        "LOG_LEVEL": "DEBUG",
        "LLM_PROVIDER": "ollama",
        "LLM_MODEL_NAME": "llama3.1:8b",
        # "LLM_MODEL_NAME": "gemini-2.0-flash-lite-001",
        "TOOL_LLM_MODEL": "llama3.1:8b",
        "OLLAMA_KEEP_ALIVE": "0",
        "OLLAMA_BASE_URL": "http://213.173.107.68:14280",
        "OLLAMA_NUM_CTX": 65536,
        "EDITOR_NODE_MAX_OUTPUT_TOKENS_OLLAMA": 16384,
        "LOG_FORMAT": "console",
        "CORS_ALLOW_ORIGINS": [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        "MAX_BATCHES": None,
        "MAX_PROCEDURES_DEV": None,
    })

# prd
if ENVIRONMENT == "prd":
    CONSTANTS.update({
        "LOG_LEVEL": "INFO",
        "LOG_FORMAT": "json",
        "CORS_ALLOW_ORIGINS": [
            "https://www.hit8.io",
            "https://hit8.io",
            "https://hit8.pages.dev",
        ],
    })

