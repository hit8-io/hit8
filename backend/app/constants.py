"""
Application constants and configuration.
"""
from __future__ import annotations

import os
from typing import Any, Literal

ENVIRONMENT: Literal["dev", "prd"] = os.getenv("ENVIRONMENT", "dev")

# Defaults
CONSTANTS: dict[str, Any] = {
    "APP_NAME": "Hit8 Chat API",
    "APP_VERSION": "0.2.0",
    "VERTEX_AI_MODEL_NAME": "gemini-3-flash-preview",
    "VERTEX_AI_LOCATION": "global",
    "CORS_ALLOW_CREDENTIALS": True,
    "ACCOUNT": "hit8",
    "ORG": "opgroeien",
    "PROJECT": "poc",
    "FLOW": "chat",
    "PROMPTS_DIR": "app/prompts",
    "LANGFUSE_ENABLED": False,
    "LANGFUSE_PUBLIC_KEY": None,
    "LANGFUSE_SECRET_KEY": None,
    "LANGFUSE_BASE_URL": None,
}

# dev
if ENVIRONMENT == "dev":
    CONSTANTS.update({
        "LOG_LEVEL": "DEBUG",
        "LOG_FORMAT": "console",
        "CORS_ALLOW_ORIGINS": [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
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

