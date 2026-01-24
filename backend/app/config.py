"""
Unified configuration management: constants + environment variables with validation.
"""
from __future__ import annotations

import json
import os
import threading
from typing import Any

import structlog
from pydantic import BaseModel, Field, computed_field, field_validator, model_validator
import json
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from app import constants

logger = structlog.get_logger(__name__)


class LLMConfig(BaseModel):
    """Configuration for a single LLM model."""
    MODEL_NAME: str
    PROVIDER: str
    LOCATION: str | None = None
    THINKING_LEVEL: str | None = None
    TEMPERATURE: float | None = None


class LLMProviderConfig(BaseModel):
    """Configuration for an LLM provider."""
    PROVIDER: str
    # Vertex AI specific
    VERTEX_AI_MAX_RETRIES: int | None = None
    # Ollama specific
    OLLAMA_KEEP_ALIVE: str | None = None
    OLLAMA_BASE_URL: str | None = None
    OLLAMA_NUM_CTX: int | None = None
    OLLAMA_EDITOR_NODE_MAX_OUTPUT_TOKENS: int | None = None


def _load_doppler_secrets() -> None:
    """Load Doppler secrets into environment variables (for Cloud Run).
    
    Reads secrets from DOPPLER_SECRETS_JSON and sets them as individual
    environment variables. Existing environment variables are never overridden.
    """
    doppler_secrets_json = os.getenv("DOPPLER_SECRETS_JSON")
    if not doppler_secrets_json:
        logger.warning(
            "doppler_secrets_missing",
            environment=os.getenv("ENVIRONMENT", "unknown"),
        )
        return
    
    try:
        secrets = json.loads(doppler_secrets_json)
        logger.info(
            "doppler_secrets_loaded",
            secret_count=len(secrets),
            environment=os.getenv("ENVIRONMENT", "unknown"),
        )
        
        for key, value in secrets.items():
            if key not in os.environ:
                os.environ[key] = str(value)
    except json.JSONDecodeError as e:
        logger.error(
            "doppler_secrets_parse_error",
            error=str(e),
            environment=os.getenv("ENVIRONMENT", "unknown"),
        )
        raise


def _load_constants_config(settings_fields: set[str] | None = None) -> dict[str, Any]:
    """Load configuration from constants module.
    
    All configuration uses uppercase keys (e.g., APP_NAME).
    Automatically loads all constants from constants.CONSTANTS dictionary.
    Only includes constants that are defined in the Settings model.
    """
    if settings_fields is None:
        # Get Settings fields from the class (defined later in this module)
        # This avoids circular import by using a parameter
        settings_fields = set(Settings.model_fields.keys())
    
    # Log constants loading
    current_env = os.getenv("ENVIRONMENT", "unknown")
    logger.debug(
        "loading_constants_config",
        environment=current_env,
        constants_env=constants.ENVIRONMENT,
        has_log_level="LOG_LEVEL" in constants.CONSTANTS,
        has_log_format="LOG_FORMAT" in constants.CONSTANTS,
        has_cors_origins="CORS_ALLOW_ORIGINS" in constants.CONSTANTS,
    )
    
    # Filter constants to only include Settings fields
    config = {
        key: value 
        for key, value in constants.CONSTANTS.items() 
        if key in settings_fields
    }
    
    return config


class ConstantsConfigSettingsSource(PydanticBaseSettingsSource):
    """Custom settings source that loads configuration from constants.py."""
    
    def __init__(self, settings_cls: type[BaseSettings]):
        super().__init__(settings_cls)
        self._settings_cls = settings_cls
    
    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        return super().get_field_value(field, field_name)
    
    def __call__(self) -> dict[str, Any]:
        # Get Settings fields to automatically filter constants
        settings_fields = set(self._settings_cls.model_fields.keys())
        return _load_constants_config(settings_fields)


class Settings(BaseSettings):
    """Application settings with validation and metadata."""
    
    # App metadata
    APP_NAME: str
    APP_VERSION: str
    ACCOUNT: str
    
    # Logging
    LOG_LEVEL: str
    LOG_FORMAT: str
    
    # CORS
    CORS_ALLOW_ORIGINS: list[str]
    CORS_ALLOW_CREDENTIALS: bool
    
    # LLM Configuration
    LLM: list[LLMConfig]
    LLM_PROVIDER: list[LLMProviderConfig]
    
    @field_validator("LLM", mode="before")
    @classmethod
    def parse_llm_config(cls, v: str | list[dict[str, Any]] | list[LLMConfig] | Any) -> list[dict[str, Any]]:
        """Parse LLM config from various formats.
        
        Supports:
        - JSON string: '[{"MODEL_NAME": "...", "PROVIDER": "...", ...}]'
        - List of dicts: [{"MODEL_NAME": "...", ...}]
        - List of LLMConfig objects (will be converted to dicts)
        """
        if isinstance(v, list):
            # Convert list of LLMConfig to list of dicts if needed
            if v and isinstance(v[0], LLMConfig):
                return [item.model_dump() for item in v]
            # Already a list of dicts
            return v
        if isinstance(v, str):
            # Try parsing as JSON
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
                # Single object, wrap in list
                return [parsed] if isinstance(parsed, dict) else [{"MODEL_NAME": str(parsed), "PROVIDER": "vertex", "LOCATION": None, "THINKING_LEVEL": None, "TEMPERATURE": None}]
            except (json.JSONDecodeError, TypeError):
                # Not JSON, treat as single model name (backward compatibility)
                return [{"MODEL_NAME": v, "PROVIDER": "vertex", "LOCATION": None, "THINKING_LEVEL": None, "TEMPERATURE": None}]
        # Fallback
        return [{"MODEL_NAME": str(v), "PROVIDER": "vertex", "LOCATION": None, "THINKING_LEVEL": None, "TEMPERATURE": None}]
    
    @field_validator("LLM_PROVIDER", mode="before")
    @classmethod
    def parse_llm_provider_config(cls, v: str | list[dict[str, Any]] | list[LLMProviderConfig] | Any) -> list[dict[str, Any]]:
        """Parse LLM_PROVIDER config from various formats.
        
        Supports:
        - JSON string: '[{"provider": "...", ...}]'
        - List of dicts: [{"provider": "...", ...}]
        - List of LLMProviderConfig objects (will be converted to dicts)
        """
        if isinstance(v, list):
            # Convert list of LLMProviderConfig to list of dicts if needed
            if v and isinstance(v[0], LLMProviderConfig):
                return [item.model_dump() for item in v]
            # Already a list of dicts
            return v
        if isinstance(v, str):
            # Try parsing as JSON
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
                # Single object, wrap in list
                return [parsed] if isinstance(parsed, dict) else []
            except (json.JSONDecodeError, TypeError):
                # Not JSON, return empty list
                return []
        # Fallback
        return []
    
    # Legacy fields for backward compatibility (deprecated)
    OLLAMA_BASE_URL: str | None = None  # Deprecated, use LLM_PROVIDER[].ollama_base_url
    OLLAMA_NUM_CTX: int | None = None  # Deprecated, use LLM_PROVIDER[].ollama_num_ctx
    OLLAMA_KEEP_ALIVE: str = "0"  # Deprecated, use LLM_PROVIDER[].ollama_keep_alive
    VERTEX_AI_LOCATION: str | None = None  # Deprecated, use LLM[].location
    GCP_PROJECT: str
    VERTEX_SERVICE_ACCOUNT: str = Field(exclude=True)
    
    # Database
    DATABASE_CONNECTION_STRING: str = Field(exclude=True)
    DATABASE_SSL_ROOT_CERT: str | None = Field(
        default=None,
        exclude=True,
        description="SSL root certificate content (not file path) - required in production"
    )
    
    @field_validator("DATABASE_SSL_ROOT_CERT")
    @classmethod
    def validate_ssl_cert_required_in_production(cls, v: str | None) -> str | None:
        """Validate that SSL certificate is provided in production."""
        if constants.ENVIRONMENT == "prd" and not v:
            raise ValueError("DATABASE_SSL_ROOT_CERT is required in production environment")
        return v
    
    # Google Identity Platform
    GOOGLE_IDENTITY_PLATFORM_DOMAIN: str
    
    # Langfuse
    LANGFUSE_ENABLED: bool
    LANGFUSE_PUBLIC_KEY: str | None = None
    LANGFUSE_SECRET_KEY: str | None = Field(default=None, exclude=True)
    
    # API
    API_TOKEN: str = Field(exclude=True)
    
    # BrightData
    BRIGHTDATA_API_KEY: str = Field(exclude=True)
    
    # Prompts
    PROMPTS_DIR: str
    
    # Agent configuration
    FLOW: str
    
    @computed_field
    @property
    def environment(self) -> str:
        """Current environment (dev, stg, or prd)."""
        return constants.ENVIRONMENT
    
    @computed_field
    @property
    def metadata(self) -> dict[str, str]:
        """Centralized metadata for tracing and logging."""
        return {
            "environment": self.environment,
            "account": self.ACCOUNT,
            "org": constants.CONSTANTS["ORG"],
            "project": constants.CONSTANTS["PROJECT"],
        }
    
    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=True,
        populate_by_name=True,
        env_file=None,
    )
    
    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Customize settings sources: constants first, then env vars (which override)."""
        return (
            init_settings,
            ConstantsConfigSettingsSource(settings_cls),  # Constants provide defaults (auto-filters to Settings fields)
            env_settings,  # Env vars override constants
            dotenv_settings,
            file_secret_settings,
        )
    
    @classmethod
    def load(cls) -> "Settings":
        """Load settings from constants and environment variables.
        
        Loading order:
        1. Doppler secrets (sets env vars)
        2. Constants config (defaults + environment-specific) via custom source
        3. Environment variables (override constants)
        
        All configuration uses uppercase keys.
        Pydantic will raise ValidationError if required Settings fields are missing.
        """
        # 1. Load Doppler secrets first (sets env vars)
        _load_doppler_secrets()
        
        # 2. Create Settings: Pydantic will use custom sources
        # All configuration uses uppercase keys
        # If Settings fields are missing from CONSTANTS, Pydantic will raise ValidationError
        return cls()


_settings_instance: Settings | None = None
_settings_lock = threading.Lock()


def get_settings() -> Settings:
    """Get Settings instance (thread-safe singleton)."""
    global _settings_instance
    if _settings_instance is None:
        with _settings_lock:
            if _settings_instance is None:
                _settings_instance = Settings.load()
    return _settings_instance


# Export singleton
settings = get_settings()
