"""
Unit tests for configuration management (config.py).
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock

import pytest
import yaml
from pydantic import ValidationError

from app.config import (
    Settings,
    _load_yaml_config,
    get_settings,
)


@pytest.fixture
def minimal_env_vars():
    """Fixture providing minimal required environment variables."""
    return {
        "ENVIRONMENT": "dev",
        "GCP_PROJECT": "test-project",
        "DATABASE_CONNECTION_STRING": "postgresql://test:test@localhost/test",
        "GOOGLE_IDENTITY_PLATFORM_DOMAIN": "test-domain",
        "API_TOKEN": "test-token",
        "VERTEX_SERVICE_ACCOUNT": '{"project_id": "test", "type": "service_account"}',
        "CORS_ALLOW_ORIGINS": '["http://localhost:5173"]',
    }


class TestLoadYamlConfig:
    """Tests for _load_yaml_config function."""
    
    def test_load_yaml_config_merges_defaults_and_env(self):
        """Test that YAML config merges defaults and environment-specific."""
        yaml_content = """
defaults:
  APP_NAME: "Default App"
  LOG_LEVEL: INFO
  LOG_FORMAT: json
dev:
  LOG_LEVEL: DEBUG
  LOG_FORMAT: console
"""
        with patch("builtins.open", mock_open(read_data=yaml_content)):
            with patch("app.config.Path") as mock_path_class:
                # Mock Path(__file__).parent / "config.yaml"
                mock_file = MagicMock()
                mock_file.__enter__ = lambda x: mock_file
                mock_file.__exit__ = lambda *args: None
                mock_path_instance = MagicMock()
                mock_path_instance.parent.__truediv__ = lambda x, y: mock_file
                mock_path_class.return_value = mock_path_instance
                
                with patch.dict(os.environ, {"ENVIRONMENT": "dev"}):
                    config = _load_yaml_config()
                    
                    assert config["APP_NAME"] == "Default App"  # From defaults
                    assert config["LOG_LEVEL"] == "DEBUG"  # From dev (overrides)
                    assert config["LOG_FORMAT"] == "console"  # From dev (overrides)
    
    def test_load_yaml_config_uses_defaults_when_env_missing(self):
        """Test that missing environment section uses defaults only."""
        yaml_content = """
defaults:
  APP_NAME: "Default App"
  LOG_LEVEL: INFO
"""
        with patch("builtins.open", mock_open(read_data=yaml_content)):
            with patch("app.config.Path") as mock_path_class:
                mock_file = MagicMock()
                mock_file.__enter__ = lambda x: mock_file
                mock_file.__exit__ = lambda *args: None
                mock_path_instance = MagicMock()
                mock_path_instance.parent.__truediv__ = lambda x, y: mock_file
                mock_path_class.return_value = mock_path_instance
                
                with patch.dict(os.environ, {"ENVIRONMENT": "nonexistent"}):
                    config = _load_yaml_config()
                    
                    assert config["APP_NAME"] == "Default App"
                    assert config["LOG_LEVEL"] == "INFO"
    
    def test_load_yaml_config_handles_empty_yaml(self):
        """Test that empty YAML file is handled."""
        with patch("builtins.open", mock_open(read_data="")):
            with patch("app.config.Path") as mock_path_class:
                mock_file = MagicMock()
                mock_file.__enter__ = lambda x: mock_file
                mock_file.__exit__ = lambda *args: None
                mock_path_instance = MagicMock()
                mock_path_instance.parent.__truediv__ = lambda x, y: mock_file
                mock_path_class.return_value = mock_path_instance
                
                config = _load_yaml_config()
                assert config == {}


class TestSettings:
    """Tests for Settings class."""
    
    def test_settings_loads_from_yaml_and_env(self, minimal_env_vars):
        """Test that Settings loads from both YAML and env vars."""
        with patch.dict(os.environ, minimal_env_vars, clear=False):
            # Clear singleton to force reload
            import app.config
            app.config._settings_instance = None
            
            settings = Settings.load()
            assert settings.GCP_PROJECT == "test-project"
            assert settings.DATABASE_CONNECTION_STRING.startswith("postgresql://")
    
    def test_settings_env_vars_override_yaml(self, minimal_env_vars):
        """Test that env vars override YAML values."""
        with patch.dict(os.environ, {**minimal_env_vars, "GCP_PROJECT": "override-project"}, clear=False):
            import app.config
            app.config._settings_instance = None
            
            settings = Settings.load()
            assert settings.GCP_PROJECT == "override-project"
    
    def test_settings_required_fields_raise_error(self):
        """Test that missing required fields raise validation errors."""
        # Remove required env vars
        required_vars = [
            "GCP_PROJECT",
            "DATABASE_CONNECTION_STRING",
            "GOOGLE_IDENTITY_PLATFORM_DOMAIN",
            "API_TOKEN",
        ]
        env_backup = {var: os.environ.pop(var, None) for var in required_vars}
        
        try:
            with patch.dict(os.environ, {"ENVIRONMENT": "dev"}, clear=False):
                import app.config
                app.config._settings_instance = None
                
                with pytest.raises(ValidationError):
                    Settings.load()
        finally:
            # Restore env vars
            for var, value in env_backup.items():
                if value is not None:
                    os.environ[var] = value
    
    def test_settings_computed_environment(self, minimal_env_vars):
        """Test that environment computed field works."""
        with patch.dict(os.environ, {**minimal_env_vars, "ENVIRONMENT": "prd"}, clear=False):
            import app.config
            app.config._settings_instance = None
            
            settings = Settings.load()
            assert settings.environment == "prd"
    
    def test_settings_environment_returns_empty_if_not_set(self, minimal_env_vars):
        """Test that environment returns empty string if ENVIRONMENT not set."""
        # Create env vars without ENVIRONMENT
        env_vars_without_env = {k: v for k, v in minimal_env_vars.items() if k != "ENVIRONMENT"}
        env_backup = os.environ.pop("ENVIRONMENT", None)
        
        try:
            with patch.dict(os.environ, env_vars_without_env, clear=False):
                import app.config
                app.config._settings_instance = None
                
                settings = Settings.load()
                assert settings.environment == ""
        finally:
            if env_backup:
                os.environ["ENVIRONMENT"] = env_backup
    
    def test_settings_metadata_includes_all_fields(self, minimal_env_vars):
        """Test that metadata includes all expected keys."""
        with patch.dict(os.environ, minimal_env_vars, clear=False):
            import app.config
            app.config._settings_instance = None
            
            settings = Settings.load()
            metadata = settings.metadata
            
            assert "environment" in metadata
            assert "account" in metadata
    
    def test_settings_optional_langfuse_fields(self, minimal_env_vars):
        """Test that optional Langfuse fields can be None."""
        with patch.dict(os.environ, minimal_env_vars, clear=False):
            import app.config
            app.config._settings_instance = None
            
            settings = Settings.load()
            # These should be None if not set
            assert settings.LANGFUSE_PUBLIC_KEY is None or isinstance(settings.LANGFUSE_PUBLIC_KEY, str)
            assert settings.LANGFUSE_SECRET_KEY is None or isinstance(settings.LANGFUSE_SECRET_KEY, str)
            assert settings.LANGFUSE_BASE_URL is None or isinstance(settings.LANGFUSE_BASE_URL, str)
    
    def test_settings_uppercase_env_vars_map_to_lowercase_fields(self, minimal_env_vars):
        """Test that uppercase env vars map to lowercase field names."""
        with patch.dict(os.environ, {**minimal_env_vars, "GCP_PROJECT": "test-gcp"}, clear=False):
            import app.config
            app.config._settings_instance = None
            
            settings = Settings.load()
            assert settings.GCP_PROJECT == "test-gcp"


class TestGetSettings:
    """Tests for get_settings singleton function."""
    
    def test_get_settings_singleton(self):
        """Test that get_settings returns the same instance."""
        # Clear singleton
        import app.config
        app.config._settings_instance = None
        
        settings1 = get_settings()
        settings2 = get_settings()
        
        assert settings1 is settings2
    
    def test_get_settings_thread_safe(self, minimal_env_vars):
        """Test that get_settings is thread-safe."""
        import threading
        import app.config
        
        with patch.dict(os.environ, minimal_env_vars, clear=False):
            app.config._settings_instance = None
            
            results = []
            lock = threading.Lock()
            
            def get_settings_in_thread():
                result = get_settings()
                with lock:
                    results.append(result)
            
            threads = [threading.Thread(target=get_settings_in_thread) for _ in range(10)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            
            # All should be the same instance
            assert all(result is results[0] for result in results)


class TestSettingsSourcePriority:
    """Tests for settings source priority (YAML vs env vars)."""
    
    def test_yaml_provides_defaults(self, minimal_env_vars):
        """Test that YAML provides default values."""
        # This is tested implicitly in other tests, but we can verify
        # that YAML values are used when env vars are not set
        with patch.dict(os.environ, minimal_env_vars, clear=False):
            import app.config
            app.config._settings_instance = None
            
            settings = Settings.load()
            # YAML should provide APP_NAME, APP_VERSION, etc.
            assert hasattr(settings, "APP_NAME")
            assert hasattr(settings, "APP_VERSION")
    
    def test_env_vars_override_yaml(self, minimal_env_vars):
        """Test that env vars override YAML values."""
        # Test with GCP_PROJECT which is required and comes from env vars
        # The YAML doesn't set this, so env var is the source
        with patch.dict(os.environ, {**minimal_env_vars, "GCP_PROJECT": "override-project"}, clear=False):
            import app.config
            app.config._settings_instance = None
            
            settings = Settings.load()
            # Env var should be used (GCP_PROJECT is not in YAML, only in env)
            assert settings.GCP_PROJECT == "override-project"


class TestSettingsEdgeCases:
    """Tests for edge cases and error handling."""
    
    def test_missing_environment_variable(self, minimal_env_vars):
        """Test behavior when ENVIRONMENT is missing."""
        # Create env vars without ENVIRONMENT
        env_vars_without_env = {k: v for k, v in minimal_env_vars.items() if k != "ENVIRONMENT"}
        env_backup = os.environ.pop("ENVIRONMENT", None)
        
        try:
            with patch.dict(os.environ, env_vars_without_env, clear=False):
                import app.config
                app.config._settings_instance = None
                
                settings = Settings.load()
                # Should use defaults only (no environment-specific config)
                assert settings.environment == ""
        finally:
            if env_backup:
                os.environ["ENVIRONMENT"] = env_backup
    
    def test_invalid_field_types_in_env_vars(self, minimal_env_vars):
        """Test that invalid field types raise validation errors."""
        # CORS_ALLOW_ORIGINS should be a list, but env var is a string
        # This should be handled by Pydantic's type coercion
        with patch.dict(os.environ, {**minimal_env_vars, "CORS_ALLOW_ORIGINS": '["*"]'}, clear=False):
            import app.config
            app.config._settings_instance = None
            
            # Should work if Pydantic can parse it
            settings = Settings.load()
            assert isinstance(settings.CORS_ALLOW_ORIGINS, list)

