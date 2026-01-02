"""
Application startup and initialization.
"""
from __future__ import annotations

import json
import logging
import logging.config
import os
import yaml
from pathlib import Path

import structlog

from app.logging import configure_structlog

# Initialize structlog before other imports that might use logging
configure_structlog()


def parse_doppler_secrets() -> None:
    """Parse Doppler secrets JSON if provided (for Cloud Run)."""
    logger = structlog.get_logger(__name__)
    
    doppler_secrets_json = os.getenv("DOPPLER_SECRETS_JSON")
    if not doppler_secrets_json:
        logger.debug("doppler_secrets_json_not_found")
        return
    
    try:
        secrets = json.loads(doppler_secrets_json)
        logger.info("doppler_secrets_json_parsed", secret_count=len(secrets))
        
        # Set individual environment variables from Doppler secrets
        set_count = 0
        skipped_count = 0
        for key, value in secrets.items():
            if key not in os.environ:
                os.environ[key] = str(value)
                set_count += 1
            else:
                skipped_count += 1
        
        logger.info(
            "doppler_secrets_loaded",
            secrets_set=set_count,
            secrets_skipped=skipped_count,
        )
    except json.JSONDecodeError as e:
        logger.error("doppler_secrets_json_invalid", error=str(e), error_type=type(e).__name__)
        raise
    except Exception as e:
        logger.exception("doppler_secrets_parse_error", error=str(e), error_type=type(e).__name__)
        raise


def setup_logging() -> None:
    """Setup logging from config.yaml."""
    config_file = Path(__file__).parent / "config.yaml"
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_file}")
    
    with open(config_file) as f:
        config_data = yaml.safe_load(f)
        if config_data is None:
            config_data = {}
    
    env = "prd" if os.getenv("ENVIRONMENT") == "prd" else "dev"
    defaults = config_data.get("defaults", {})
    env_config = config_data.get(env, {})
    
    # Merge logging config (env overrides defaults)
    logging_config = defaults.get("logging", {})
    if "logging" in env_config:
        logging_config = {**logging_config, **env_config["logging"]}
    
    if logging_config:
        logging.config.dictConfig(logging_config)


def setup_debugpy() -> None:
    """Enable debugpy for remote debugging if log_level is DEBUG and DEBUG env var is not set.
    
    Note: If DEBUG=true is set, debugpy is already started via command line in docker-compose.yml,
    so we skip initialization here to avoid conflicts.
    """
    try:
        # If DEBUG env var is set, debugpy is already running via command line
        if os.getenv("DEBUG") == "true":
            structlog.get_logger(__name__).debug("debugpy_already_running_via_command")
            return
        
        from app.config import settings
        import debugpy
        
        # Only initialize if log_level is DEBUG and DEBUG env var is not set
        if settings.log_level.upper() == "DEBUG":
            debugpy.listen(("0.0.0.0", 5678))
            structlog.get_logger(__name__).info("debugpy_listening", port=5678)
    except ImportError:
        pass  # debugpy not installed, skip
    except Exception as e:
        structlog.get_logger(__name__).warning("debugpy_init_failed", error=str(e))


def initialize_app() -> None:
    """Initialize the application: parse secrets, setup logging, etc."""
    # Parse Doppler secrets FIRST, before importing settings
    parse_doppler_secrets()
    
    # Import settings after secrets are parsed
    from app.config import settings
    
    # Setup logging from config.yaml
    try:
        setup_logging()
    except Exception as e:
        structlog.get_logger(__name__).warning("logging_setup_failed", error=str(e))
    
    # Setup debugpy if in DEBUG mode
    setup_debugpy()
    
    # Log startup information
    logger = structlog.get_logger(__name__)
    try:
        env_vars_to_check = [
            "ENVIRONMENT", "GCP_PROJECT", "GOOGLE_IDENTITY_PLATFORM_DOMAIN",
            "DATABASE_CONNECTION_STRING", "VERTEX_HIT8_POC_IAM_GSERVICEACCOUNT_COM",
        ]
        present_vars = {var: "SET" if os.getenv(var) else "MISSING" for var in env_vars_to_check}
        logger.info("startup_env_check", environment_vars=present_vars)
    except Exception:
        pass  # Non-critical, continue startup

