"""
Configuration management using Pydantic Settings with YAML and environment variable support.
"""
from __future__ import annotations

from typing import Any
from pathlib import Path
import os
import yaml
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, PydanticBaseSettingsSource


class YamlConfigSettingsSource(PydanticBaseSettingsSource):
    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        return super().get_field_value(field, field_name)

    def __call__(self) -> dict[str, Any]:
        yaml_file = Path(__file__).parent / "config.yaml"
        if not yaml_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {yaml_file}")
        
        with open(yaml_file) as f:
            config_data = yaml.safe_load(f)
            if config_data is None:
                config_data = {}
        
        env = "prd" if os.getenv("ENVIRONMENT") == "prd" else "dev"
        defaults = config_data.get("defaults", {})
        env_config = config_data.get(env, {})
        
        # Merge configs and exclude 'logging' section (handled separately)
        merged = {**defaults, **env_config}
        merged.pop("logging", None)  # Remove logging section from Settings
        return merged


class Settings(BaseSettings):
    app_name: str = Field(...)
    app_version: str = Field(...)
    log_level: str = Field(...)
    log_format: str = Field(...)
    cors_allow_origins: list[str] = Field(...)
    cors_allow_credentials: bool = Field(...)
    vertex_ai_model_name: str = Field(...)
    vertex_ai_location: str = Field(...)
    gcp_project: str = Field(..., validation_alias="GCP_PROJECT")
    google_identity_platform_domain: str = Field(..., validation_alias="GOOGLE_IDENTITY_PLATFORM_DOMAIN")
    supabase_url: str = Field(...)
    vertex_service_account_json: str = Field(..., validation_alias="VERTEX_HIT8_POC_IAM_GSERVICEACCOUNT_COM", exclude=True)
    # Langfuse configuration
    langfuse_enabled: bool = Field(...)
    langfuse_public_key: str | None = Field(None, validation_alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str | None = Field(None, validation_alias="LANGFUSE_SECRET_KEY")
    langfuse_base_url: str | None = Field(None, validation_alias="LANGFUSE_BASE_URL")
    # Centralized metadata
    customer: str = Field(...)
    project: str = Field(...)

    @model_validator(mode="after")
    def validate_langfuse_config(self) -> "Settings":
        """Validate Langfuse configuration - require secrets when enabled."""
        if self.langfuse_enabled:
            if not self.langfuse_public_key:
                raise ValueError("LANGFUSE_PUBLIC_KEY is required when langfuse_enabled=True")
            if not self.langfuse_secret_key:
                raise ValueError("LANGFUSE_SECRET_KEY is required when langfuse_enabled=True")
            if not self.langfuse_base_url:
                raise ValueError("LANGFUSE_BASE_URL is required when langfuse_enabled=True")
        return self

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
        return (
            init_settings,
            env_settings,
            YamlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )


settings = Settings()


def get_metadata() -> dict[str, str]:
    """
    Get centralized metadata (environment, customer, project).
    
    Returns:
        dict with keys: environment, customer, project
    """
    import os
    environment = "prd" if os.getenv("ENVIRONMENT") == "prd" else "dev"
    return {
        "environment": environment,
        "customer": settings.customer,
        "project": settings.project,
    }

