"""
Unit tests for prompt loader (prompts/loader.py).
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml

# Set required env vars before importing loader (which imports settings)
os.environ.setdefault("DATABASE_CONNECTION_STRING", "postgresql://test:test@localhost/test")
os.environ.setdefault("API_TOKEN", "test-token")
os.environ.setdefault("ENVIRONMENT", "dev")

from app.prompts.loader import (
    PromptObject,
    load_prompt,
    get_system_prompt,
    _prompt_cache,
)


@pytest.fixture
def temp_prompts_dir():
    """Create a temporary directory for prompt files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_prompt_yaml():
    """Sample valid prompt YAML content."""
    return {
        "prompt": "Hello {{ name }}, welcome to {{ service }}!",
        "version": "1.0.0",
        "config": {"temperature": 0.7},
    }


@pytest.fixture
def create_prompt_file(temp_prompts_dir, sample_prompt_yaml):
    """Helper to create a prompt file in temp directory."""
    def _create(name: str, content: dict | None = None):
        file_path = temp_prompts_dir / f"{name}.yaml"
        with open(file_path, "w", encoding="utf-8") as f:
            yaml.dump(content or sample_prompt_yaml, f)
        return file_path
    return _create


class TestPromptObject:
    """Tests for PromptObject class."""
    
    def test_render_basic(self):
        """Test rendering a prompt without variables."""
        obj = PromptObject(
            template_text="Hello world",
            version="1.0.0",
            config={},
        )
        result = obj.render()
        assert result == "Hello world"
    
    def test_render_with_variables(self):
        """Test rendering a prompt with variables."""
        obj = PromptObject(
            template_text="Hello {{ name }}, you are {{ age }} years old.",
            version="1.0.0",
            config={},
        )
        result = obj.render(name="Alice", age=30)
        assert result == "Hello Alice, you are 30 years old."
    
    def test_render_with_conditionals(self):
        """Test rendering with Jinja2 conditionals."""
        obj = PromptObject(
            template_text="Hello{% if premium %} Premium{% endif %} user!",
            version="1.0.0",
            config={},
        )
        assert obj.render(premium=True) == "Hello Premium user!"
        assert obj.render(premium=False) == "Hello user!"
    
    def test_render_missing_variable_raises_error(self):
        """Test that missing required variables raise an error."""
        obj = PromptObject(
            template_text="Hello {{ name }}",
            version="1.0.0",
            config={},
        )
        with pytest.raises(ValueError, match="Failed to render prompt"):
            obj.render()
    
    def test_render_invalid_template_raises_error(self):
        """Test that invalid template syntax raises an error."""
        obj = PromptObject(
            template_text="Hello {{ name }",  # Missing closing brace
            version="1.0.0",
            config={},
        )
        with pytest.raises(ValueError, match="Failed to render prompt"):
            obj.render(name="Alice")


class TestLoadPrompt:
    """Tests for load_prompt function."""
    
    def test_load_prompt_success(self, temp_prompts_dir, create_prompt_file):
        """Test successfully loading a prompt file."""
        create_prompt_file("test_prompt")
        
        with patch("app.prompts.loader.PROMPTS_DIR", temp_prompts_dir):
            with patch("app.prompts.loader.IS_DEV", True):
                # Clear cache
                _prompt_cache.clear()
                
                result = load_prompt("test_prompt")
                
                assert isinstance(result, PromptObject)
                assert result.template_text == "Hello {{ name }}, welcome to {{ service }}!"
                assert result.version == "1.0.0"
                assert result.config == {"temperature": 0.7}
    
    def test_load_prompt_with_default_version(self, temp_prompts_dir, create_prompt_file):
        """Test loading a prompt without version defaults to 1.0.0."""
        content = {"prompt": "Test prompt"}
        create_prompt_file("test_prompt", content)
        
        with patch("app.prompts.loader.PROMPTS_DIR", temp_prompts_dir):
            with patch("app.prompts.loader.IS_DEV", True):
                _prompt_cache.clear()
                
                result = load_prompt("test_prompt")
                assert result.version == "1.0.0"
    
    def test_load_prompt_with_default_config(self, temp_prompts_dir, create_prompt_file):
        """Test loading a prompt without config defaults to empty dict."""
        content = {"prompt": "Test prompt", "version": "2.0.0"}
        create_prompt_file("test_prompt", content)
        
        with patch("app.prompts.loader.PROMPTS_DIR", temp_prompts_dir):
            with patch("app.prompts.loader.IS_DEV", True):
                _prompt_cache.clear()
                
                result = load_prompt("test_prompt")
                assert result.config == {}
    
    def test_load_prompt_file_not_found(self, temp_prompts_dir):
        """Test that missing prompt file raises FileNotFoundError."""
        with patch("app.prompts.loader.PROMPTS_DIR", temp_prompts_dir):
            with patch("app.prompts.loader.IS_DEV", True):
                _prompt_cache.clear()
                
                with pytest.raises(FileNotFoundError, match="Prompt file not found"):
                    load_prompt("nonexistent")
    
    def test_load_prompt_invalid_yaml(self, temp_prompts_dir):
        """Test that invalid YAML raises ValueError."""
        file_path = temp_prompts_dir / "invalid.yaml"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("invalid: yaml: content: [")
        
        with patch("app.prompts.loader.PROMPTS_DIR", temp_prompts_dir):
            with patch("app.prompts.loader.IS_DEV", True):
                _prompt_cache.clear()
                
                with pytest.raises(ValueError, match="Failed to parse YAML"):
                    load_prompt("invalid")
    
    def test_load_prompt_missing_prompt_key(self, temp_prompts_dir, create_prompt_file):
        """Test that missing 'prompt' key raises ValueError."""
        content = {"version": "1.0.0"}
        create_prompt_file("test_prompt", content)
        
        with patch("app.prompts.loader.PROMPTS_DIR", temp_prompts_dir):
            with patch("app.prompts.loader.IS_DEV", True):
                _prompt_cache.clear()
                
                with pytest.raises(ValueError, match="Invalid prompt file format"):
                    load_prompt("test_prompt")
    
    def test_load_prompt_invalid_prompt_type(self, temp_prompts_dir, create_prompt_file):
        """Test that non-string prompt raises ValueError."""
        content = {"prompt": 123}  # Should be string
        create_prompt_file("test_prompt", content)
        
        with patch("app.prompts.loader.PROMPTS_DIR", temp_prompts_dir):
            with patch("app.prompts.loader.IS_DEV", True):
                _prompt_cache.clear()
                
                with pytest.raises(ValueError, match="Prompt must be a string"):
                    load_prompt("test_prompt")
    
    def test_load_prompt_not_dict(self, temp_prompts_dir):
        """Test that non-dict YAML content raises ValueError."""
        file_path = temp_prompts_dir / "not_dict.yaml"
        with open(file_path, "w", encoding="utf-8") as f:
            yaml.dump(["list", "of", "strings"], f)
        
        with patch("app.prompts.loader.PROMPTS_DIR", temp_prompts_dir):
            with patch("app.prompts.loader.IS_DEV", True):
                _prompt_cache.clear()
                
                with pytest.raises(ValueError, match="Invalid prompt file format"):
                    load_prompt("not_dict")
    
    def test_load_prompt_caching_in_prod(self, temp_prompts_dir, create_prompt_file):
        """Test that prompts are cached in production mode."""
        create_prompt_file("test_prompt")
        
        with patch("app.prompts.loader.PROMPTS_DIR", temp_prompts_dir):
            with patch("app.prompts.loader.IS_DEV", False):
                _prompt_cache.clear()
                
                # First load
                result1 = load_prompt("test_prompt")
                
                # Delete file to verify cache is used
                (temp_prompts_dir / "test_prompt.yaml").unlink()
                
                # Second load should use cache
                result2 = load_prompt("test_prompt")
                
                assert result1 is result2  # Same object from cache
                assert "test_prompt" in _prompt_cache
    
    def test_load_prompt_no_caching_in_dev(self, temp_prompts_dir, create_prompt_file):
        """Test that prompts are NOT cached in dev mode."""
        create_prompt_file("test_prompt")
        
        with patch("app.prompts.loader.PROMPTS_DIR", temp_prompts_dir):
            with patch("app.prompts.loader.IS_DEV", True):
                _prompt_cache.clear()
                
                # First load
                result1 = load_prompt("test_prompt")
                
                # Second load should reload from disk (not cached)
                result2 = load_prompt("test_prompt")
                
                # Different objects (not cached)
                assert result1 is not result2
                # But same content
                assert result1.template_text == result2.template_text
    
    def test_load_prompt_force_refresh(self, temp_prompts_dir, create_prompt_file):
        """Test that force_refresh bypasses cache even in prod."""
        create_prompt_file("test_prompt")
        
        with patch("app.prompts.loader.PROMPTS_DIR", temp_prompts_dir):
            with patch("app.prompts.loader.IS_DEV", False):
                _prompt_cache.clear()
                
                # First load
                result1 = load_prompt("test_prompt")
                
                # Force refresh should reload
                result2 = load_prompt("test_prompt", force_refresh=True)
                
                # Different objects
                assert result1 is not result2
                # But same content
                assert result1.template_text == result2.template_text


class TestGetSystemPrompt:
    """Tests for get_system_prompt function."""
    
    def test_get_system_prompt_calls_load_prompt(self, temp_prompts_dir, create_prompt_file):
        """Test that get_system_prompt calls load_prompt with correct name."""
        create_prompt_file("system_prompt")
        
        with patch("app.prompts.loader.PROMPTS_DIR", temp_prompts_dir):
            with patch("app.prompts.loader.IS_DEV", True):
                _prompt_cache.clear()
                
                result = get_system_prompt()
                
                assert isinstance(result, PromptObject)
                assert result.template_text == "Hello {{ name }}, welcome to {{ service }}!"


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear prompt cache before and after each test."""
    _prompt_cache.clear()
    yield
    _prompt_cache.clear()

