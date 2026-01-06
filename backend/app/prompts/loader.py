"""
Prompt Service: Handles loading, caching, and templating of LLM prompts.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog
import yaml
from jinja2 import Environment, StrictUndefined

from app.config import settings

logger = structlog.get_logger(__name__)

jinja_env = Environment(undefined=StrictUndefined)
IS_DEV = settings.environment == "dev"
PROMPTS_DIR = Path(settings.prompts_dir)
_prompt_cache: dict[str, "PromptObject"] = {}


@dataclass
class PromptObject:
    """Rich prompt object with templating support."""
    
    template_text: str
    version: str
    config: dict[str, Any]

    def render(self, **kwargs: Any) -> str:
        """Render the prompt template with provided variables."""
        try:
            template = jinja_env.from_string(self.template_text)
            return template.render(**kwargs)
        except Exception as e:
            logger.error(
                "prompt_render_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise ValueError(f"Failed to render prompt: {e}") from e


def load_prompt(prompt_name: str, force_refresh: bool = False) -> PromptObject:
    """
    Load a prompt from YAML file.
    
    Args:
        prompt_name: Filename without .yaml extension
        force_refresh: Bypass cache (automatic in dev mode)
        
    Returns:
        PromptObject with render() method
        
    Raises:
        FileNotFoundError: If prompt file doesn't exist
        ValueError: If prompt file is invalid
    """
    # Return cached version if available and not in dev mode
    if not IS_DEV and not force_refresh and prompt_name in _prompt_cache:
        return _prompt_cache[prompt_name]

    prompt_file = PROMPTS_DIR / f"{prompt_name}.yaml"
    
    if not prompt_file.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_name}")

    try:
        with open(prompt_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict) or "prompt" not in data:
            raise ValueError(f"Invalid prompt file format: {prompt_file}")
        
        prompt_text = data["prompt"]
        if not isinstance(prompt_text, str):
            raise ValueError(f"Prompt must be a string: {prompt_file}")

        prompt_obj = PromptObject(
            template_text=prompt_text,
            version=str(data.get("version", "1.0.0")),
            config=data.get("config", {}),
        )

        _prompt_cache[prompt_name] = prompt_obj
        
        logger.info(
            "prompt_loaded_from_disk",
            name=prompt_name,
            version=prompt_obj.version,
            prompt_file=str(prompt_file),
        )
        
        return prompt_obj

    except yaml.YAMLError as e:
        raise ValueError(f"Failed to parse YAML: {prompt_file}: {e}") from e
    except Exception as e:
        logger.error(
            "prompt_load_failed",
            name=prompt_name,
            prompt_file=str(prompt_file),
            error=str(e),
            error_type=type(e).__name__,
        )
        raise


def get_system_prompt(agent_type: str | None = None) -> PromptObject:
    """
    Get the system prompt for the specified agent type.
    
    Args:
        agent_type: Agent type (e.g., "opgroeien", "simple"). 
                   If None, uses settings.agent_graph_type
    
    Returns:
        PromptObject with render() method
    """
    if agent_type is None:
        agent_type = settings.agent_graph_type
    
    prompt_name = f"{agent_type}_system_prompt"
    return load_prompt(prompt_name)
