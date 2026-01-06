"""
Unified configuration management: YAML + environment variables with validation.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

import structlog
import yaml
from pydantic import Field, computed_field, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

logger = structlog.get_logger(__name__)


def _load_doppler_secrets() -> None:
    """Load Doppler secrets into environment variables (for Cloud Run).
    
    Reads secrets from DOPPLER_SECRETS_JSON and sets them as individual
    environment variables. Existing environment variables are never overridden.
    """
    doppler_secrets_json = os.getenv("DOPPLER_SECRETS_JSON")
    if not doppler_secrets_json:
        return
    
    secrets = json.loads(doppler_secrets_json)
    logger.info("doppler_secrets_loaded", secret_count=len(secrets))
    
    for key, value in secrets.items():
        if key not in os.environ:
            os.environ[key] = str(value)


def _load_yaml_config() -> dict[str, Any]:
    """Load and merge YAML configuration based on environment.
    
    YAML uses uppercase keys (e.g., APP_NAME) that match the aliases generated
    by alias_generator. This allows both YAML and env vars to use the same
    uppercase naming convention.
    """
    config_file = Path(__file__).parent / "config.yaml"
    with open(config_file) as f:
        config_data = yaml.safe_load(f) or {}
    
    env = os.getenv("ENVIRONMENT")
    defaults = config_data.get("defaults", {}) or {}
    env_config = config_data.get(env, {}) or {}
    
    # Merge configs
    # YAML keys are uppercase (APP_NAME), alias_generator maps field names to uppercase
    merged = {**defaults, **env_config}
    return merged


class YamlConfigSettingsSource(PydanticBaseSettingsSource):
    """Custom settings source that loads configuration from config.yaml."""
    
    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        return super().get_field_value(field, field_name)
    
    def __call__(self) -> dict[str, Any]:
        return _load_yaml_config()


class Settings(BaseSettings):
    """Application settings with validation and metadata."""
    
    # App metadata
    app_name: str
    app_version: str
    account: str
    org: str
    project: str
    
    # Logging
    log_level: str
    log_format: str
    
    # CORS
    cors_allow_origins: list[str]
    cors_allow_credentials: bool
    
    # Vertex AI
    vertex_ai_model_name: str
    vertex_ai_location: str
    gcp_project: str
    vertex_service_account: str = Field(exclude=True)
    
    # Database
    database_connection_string: str
    
    # Google Identity Platform
    google_identity_platform_domain: str
    
    # Langfuse
    langfuse_enabled: bool
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_base_url: str | None = None
    
    # API
    api_token: str
    
    # Prompts
    prompts_dir: str
    
    # Agent configuration
    agent_graph_type: str
    
    @computed_field
    @property
    def environment(self) -> str:
        """Current environment (dev or prd)."""
        return os.getenv("ENVIRONMENT", "")
    
    @computed_field
    @property
    def metadata(self) -> dict[str, str]:
        """Centralized metadata for tracing and logging."""
        return {
            "environment": self.environment,
            "account": self.account,
            "org": self.org,
            "project": self.project,
        }
    
    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=True,
        populate_by_name=True,
        env_file=None,
        alias_generator=lambda field_name: field_name.upper(),
        validation_alias_generator=lambda field_name: field_name.upper(),
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
        """Customize settings sources: YAML first, then env vars (which override)."""
        return (
            init_settings,
            YamlConfigSettingsSource(settings_cls),  # YAML provides defaults (field names)
            env_settings,  # Env vars override YAML (uses validation_alias_generator)
            dotenv_settings,
            file_secret_settings,
        )
    
    @classmethod
    def load(cls) -> "Settings":
        """Load settings from YAML and environment variables.
        
        Loading order:
        1. Doppler secrets (sets env vars)
        2. YAML config (defaults + environment-specific) via custom source
        3. Environment variables (override YAML) via validation_alias_generator
        
        YAML and env vars both use uppercase keys (generated by validation_alias_generator).
        """
        # 1. Load Doppler secrets first (sets env vars)
        _load_doppler_secrets()
        
        # 2. Create Settings: Pydantic will use custom sources
        # YAML and env vars both use uppercase keys via validation_alias_generator
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
