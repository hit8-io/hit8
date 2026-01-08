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
    "APP_VERSION": "0.3.0",
    "LLM_MODEL_NAME": "gemini-3-pro-preview",
    "TOOL_LLM_MODEL": "gemini-2.5-flash",
    "LLM_THINKING_LEVEL": None,
    "TOOL_LLM_THINKING_LEVEL": None,
    "LLM_TEMPERATURE": None,
    "TOOL_LLM_TEMPERATURE": 0.1,
    "VERTEX_AI_LOCATION": "global",
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

