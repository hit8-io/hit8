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
PROMPTS_DIR = Path(settings.PROMPTS_DIR)
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
        prompt_name: Path relative to PROMPTS_DIR, following org/project structure.
                    Prompt paths are determined from flow constants.py (ORG, PROJECT).
                    Format: "{org}/{project}/system_prompt" (e.g., "opgroeien/poc/system_prompt")
        force_refresh: Bypass cache (automatic in dev mode)
        
    Returns:
        PromptObject with render() method
        
    Raises:
        FileNotFoundError: If prompt file doesn't exist
        ValueError: If prompt file is invalid
        
    Note:
        Use get_system_prompt() to automatically resolve prompt paths from flow constants.
        This function is a low-level loader that expects the full path.
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
    
    Derives prompt path from ORG/PROJECT/FLOW structure:
    - If agent_type is "chat" or None: uses main constants (ORG, PROJECT, FLOW)
    - Otherwise: uses flow-specific constants modules
    
    Args:
        agent_type: Agent type (e.g., "chat", "opgroeien", "simple"). 
                   If None, uses settings.FLOW
    
    Returns:
        PromptObject with render() method
    """
    if agent_type is None:
        agent_type = settings.FLOW
    
    # Special handling for "chat" flow: use main constants
    if agent_type == "chat":
        from app import constants
        org = constants.CONSTANTS["ORG"]
        project = constants.CONSTANTS["PROJECT"]
        # Import flow constants to get SYSTEM_PROMPT
        import importlib
        flow_constants_path = f"app.flows.{org}.{project}.constants"
        flow_constants = importlib.import_module(flow_constants_path)
        prompt_name = f"{org}/{project}/{flow_constants.SYSTEM_PROMPT}"
    else:
        # Map agent types to their flow constants modules
        # This allows each flow to define its own prompt path
        constants_modules = {
            "opgroeien": "app.flows.opgroeien.poc.constants",
            "simple": "app.flows.hit8.hit8.constants",
        }
        
        # Import constants module based on agent type
        if agent_type in constants_modules:
            module_path = constants_modules[agent_type]
            # Dynamic import to avoid circular dependencies
            import importlib
            constants = importlib.import_module(module_path)
            # Construct path from ORG, PROJECT, and SYSTEM_PROMPT
            prompt_name = f"{constants.ORG}/{constants.PROJECT}/{constants.SYSTEM_PROMPT}"
        else:
            # Fall back to old naming convention for unknown agent types
            prompt_name = f"{agent_type}_system_prompt"
    
    return load_prompt(prompt_name)
