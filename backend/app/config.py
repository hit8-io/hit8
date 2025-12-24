"""
Configuration management using Pydantic Settings with YAML and environment variable support.

This module implements a layered configuration strategy:
- Non-secrets: Stored in config.yaml (version-controlled)
- Secrets: Managed via environment variables
- Priority: Init args > Env Vars > YAML File > Defaults
"""
from __future__ import annotations

from typing import Any
from pathlib import Path
import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict, PydanticBaseSettingsSource


class YamlConfigSettingsSource(PydanticBaseSettingsSource):
    """Custom settings source to load configuration from config.yaml file."""
    
    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        return super().get_field_value(field, field_name)

    def __call__(self) -> dict[str, Any]:
        """Load config.yaml from the same directory as this file."""
        yaml_file = Path(__file__).parent / "config.yaml"
        if not yaml_file.exists():
            return {}
        with open(yaml_file) as f:
            return yaml.safe_load(f) or {}


class Settings(BaseSettings):
    """
    Application settings with layered configuration support.
    
    Non-secrets are loaded from config.yaml.
    Secrets must be provided via environment variables.
    """
    
    # --- Application Config (Non-Secrets) ---
    # Values loaded from config.yaml
    app_name: str = Field(..., description="Application name")
    app_version: str = Field(..., description="Application version")
    debug_mode: bool = Field(..., description="Debug mode flag")
    
    # --- CORS Configuration (Non-Secrets) ---
    # Values loaded from config.yaml
    cors_allow_origins: list[str] = Field(..., description="CORS allowed origins")
    cors_allow_credentials: bool = Field(..., description="CORS allow credentials")
    
    # --- Vertex AI Configuration (Non-Secrets) ---
    # Values loaded from config.yaml
    vertex_ai_model_name: str = Field(..., description="Vertex AI model name")
    vertex_ai_location: str = Field(..., description="Vertex AI location")
    
    # --- GCP Configuration (Non-Secrets) ---
    # Values loaded from config.yaml
    gcp_project: str = Field(..., description="GCP project ID")
    google_identity_platform_domain: str = Field(..., description="Google Identity Platform domain")
    
    # --- Supabase Configuration (Non-Secrets) ---
    # Values loaded from config.yaml
    supabase_url: str = Field(..., description="Supabase URL")
    
    # --- Secrets (From Env Vars) ---
    # Required - must be provided via environment variables
    # Using validation_alias to match exact environment variable name
    vertex_service_account_json: str = Field(
        ...,
        validation_alias="VERTEX_HIT8_POC_IAM_GSERVICEACCOUNT_COM",
        description="Vertex AI and Firebase service account JSON",
        exclude=True  # Keep it out of logs/repr
    )

    model_config = SettingsConfigDict(
        env_prefix="",  # Match env vars exactly (no prefix)
        case_sensitive=True,  # Match exact case for env vars
        populate_by_name=True,  # Allow both field name and alias
        env_file=None,  # Don't use .env files, rely on environment variables
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
        """
        Customize settings sources priority order.
        
        Priority: Init args > Env Vars > YAML File
        """
        return (
            init_settings,  # Highest priority: explicit init args
            env_settings,  # Environment variables
            YamlConfigSettingsSource(settings_cls),  # YAML file
            file_secret_settings,
        )
    
    def get_vertex_service_account(self) -> str:
        """Get Vertex AI service account JSON."""
        return self.vertex_service_account_json
    
    def get_firebase_service_account(self) -> str:
        """Get Firebase service account JSON."""
        return self.vertex_service_account_json


# Global settings instance
settings = Settings()

