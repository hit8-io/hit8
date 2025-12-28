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
    database_connection_string: str = Field(..., validation_alias="DATABASE_CONNECTION_STRING")
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


# Initialize settings with better error handling
try:
    # Validate critical environment variables before Settings initialization
    required_env_vars = [
        "GCP_PROJECT",
        "GOOGLE_IDENTITY_PLATFORM_DOMAIN",
        "DATABASE_CONNECTION_STRING",
        "VERTEX_HIT8_POC_IAM_GSERVICEACCOUNT_COM",
    ]
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        import sys
        print(f"ERROR: Missing required environment variables: {', '.join(missing_vars)}", file=sys.stderr)
        print(f"ERROR: Available env vars: {', '.join(sorted([k for k in os.environ.keys() if not k.startswith('_')]))}", file=sys.stderr)
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
    
    # Validate DATABASE_CONNECTION_STRING format
    db_conn_str = os.getenv("DATABASE_CONNECTION_STRING")
    if db_conn_str:
        if not db_conn_str.startswith("postgresql://"):
            import sys
            print(f"ERROR: DATABASE_CONNECTION_STRING does not start with 'postgresql://'", file=sys.stderr)
            print(f"ERROR: Connection string (first 50 chars): {db_conn_str[:50]}...", file=sys.stderr)
            raise ValueError("Invalid DATABASE_CONNECTION_STRING format")
    
    settings = Settings()
except Exception as e:
    import sys
    import traceback
    # Print detailed error to stderr for Cloud Run logs
    print(f"ERROR: Failed to initialize Settings: {e}", file=sys.stderr)
    print(f"ERROR: Error type: {type(e).__name__}", file=sys.stderr)
    print(f"ERROR: Traceback:", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    # Check which required fields might be missing
    required_env_vars = [
        "GCP_PROJECT",
        "GOOGLE_IDENTITY_PLATFORM_DOMAIN",
        "DATABASE_CONNECTION_STRING",
        "VERTEX_HIT8_POC_IAM_GSERVICEACCOUNT_COM",
    ]
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        print(f"ERROR: Missing environment variables: {', '.join(missing_vars)}", file=sys.stderr)
    # Also check what env vars ARE present (for debugging)
    present_vars = {var: "SET" if os.getenv(var) else "MISSING" for var in required_env_vars}
    print(f"ERROR: Environment variable status: {present_vars}", file=sys.stderr)
    raise


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

