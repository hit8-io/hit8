"""
Logging utilities for structlog integration.
"""
from __future__ import annotations

import logging
import logging.config

import structlog


# 1. Define the shared processors (used by both structlog and standard logging)
SHARED_PROCESSORS = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_logger_name,
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt="iso"),
]


# 2. Configure structlog (must be done once at startup)
def configure_structlog():
    """Configure structlog with standard library integration."""
    structlog.configure(
        processors=SHARED_PROCESSORS + [
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


# 3. Create custom formatters for structlog
class StructlogJSONFormatter(structlog.stdlib.ProcessorFormatter):
    """JSON formatter for structlog (used in production)."""
    
    def __init__(self, *args, **kwargs):
        # We hardcode the processors here so YAML doesn't need to know about them
        super().__init__(
            processor=structlog.processors.JSONRenderer(),
            foreign_pre_chain=SHARED_PROCESSORS,
            *args,
            **kwargs
        )


class StructlogConsoleFormatter(structlog.stdlib.ProcessorFormatter):
    """Console-friendly formatter for structlog (used in development)."""
    
    def __init__(self, *args, **kwargs):
        # Use console-friendly processor for development
        super().__init__(
            processor=structlog.dev.ConsoleRenderer(colors=True),
            foreign_pre_chain=SHARED_PROCESSORS,
            *args,
            **kwargs
        )


def setup_logging() -> None:
    """Setup logging using log_level and log_format from settings."""
    from app.config import settings
    
    # Determine formatter based on log_format
    if settings.LOG_FORMAT == "json":
        formatter_name = "json_formatter"
    else:  # console or any other value
        formatter_name = "console_formatter"
    
    # Build logging configuration dict
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json_formatter": {
                "()": "app.logging.StructlogJSONFormatter",
            },
            "console_formatter": {
                "()": "app.logging.StructlogConsoleFormatter",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": formatter_name,
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "": {  # Root logger
                "handlers": ["console"],
                "level": settings.LOG_LEVEL.upper(),
            },
            "app": {
                "handlers": ["console"],
                "level": settings.LOG_LEVEL.upper(),
                "propagate": False,
            },
        },
    }
    
    logging.config.dictConfig(logging_config)

