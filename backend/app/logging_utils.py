"""
Logging utilities for structlog integration with config.yaml.
"""
from __future__ import annotations

import structlog
import logging


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


# 3. Create a Custom Formatter for YAML to reference
class StructlogJSONFormatter(structlog.stdlib.ProcessorFormatter):
    """JSON formatter for structlog that can be referenced in YAML config."""
    
    def __init__(self, *args, **kwargs):
        # We hardcode the processors here so YAML doesn't need to know about them
        super().__init__(
            processor=structlog.processors.JSONRenderer(),
            foreign_pre_chain=SHARED_PROCESSORS,
            *args,
            **kwargs
        )


class StructlogConsoleFormatter(structlog.stdlib.ProcessorFormatter):
    """Console-friendly formatter for structlog that can be referenced in YAML config."""
    
    def __init__(self, *args, **kwargs):
        # Use console-friendly processor for development
        super().__init__(
            processor=structlog.dev.ConsoleRenderer(colors=True),
            foreign_pre_chain=SHARED_PROCESSORS,
            *args,
            **kwargs
        )

