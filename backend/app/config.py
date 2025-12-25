"""
Configuration management using Pydantic Settings with YAML and environment variable support.
"""
from __future__ import annotations

from typing import Any
from pathlib import Path
import os
import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict, PydanticBaseSettingsSource


class YamlConfigSettingsSource(PydanticBaseSettingsSource):
    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        return super().get_field_value(field, field_name)

    def __call__(self) -> dict[str, Any]:
        yaml_file = Path(__file__).parent / "config.yaml"
        if not yaml_file.exists():
            return {}
        
        with open(yaml_file) as f:
            config_data = yaml.safe_load(f) or {}
        
        env = "prod" if (os.getenv("K_SERVICE") or os.getenv("ENVIRONMENT") == "prod") else "dev"
        defaults = config_data.get("defaults", {})
        env_config = config_data.get(env, {})
        return {**defaults, **env_config}


class Settings(BaseSettings):
    app_name: str = Field(...)
    app_version: str = Field(...)
    debug_mode: bool = Field(...)
    cors_allow_origins: list[str] = Field(...)
    cors_allow_credentials: bool = Field(...)
    vertex_ai_model_name: str = Field(...)
    vertex_ai_location: str = Field(...)
    gcp_project: str = Field(..., validation_alias="GCP_PROJECT")
    google_identity_platform_domain: str = Field(..., validation_alias="GOOGLE_IDENTITY_PLATFORM_DOMAIN")
    supabase_url: str = Field(...)
    vertex_service_account_json: str = Field(..., validation_alias="VERTEX_HIT8_POC_IAM_GSERVICEACCOUNT_COM", exclude=True)

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

