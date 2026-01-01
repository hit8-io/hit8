"""
Utility module for loading prompts from YAML files.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import yaml
import structlog

logger = structlog.get_logger(__name__)

# Cache for loaded prompts
_prompt_cache: dict[str, str] = {}


def load_prompt(prompt_name: str) -> str:
    """
    Load a prompt from a YAML file in the prompts directory.
    
    Args:
        prompt_name: Name of the prompt file (without .yaml extension)
        
    Returns:
        The prompt text as a string
        
    Raises:
        FileNotFoundError: If the prompt file doesn't exist
        ValueError: If the prompt file is invalid
    """
    # Check cache first
    if prompt_name in _prompt_cache:
        return _prompt_cache[prompt_name]
    
    # Get prompts directory (same directory as this file)
    prompts_dir = Path(__file__).parent
    prompt_file = prompts_dir / f"{prompt_name}.yaml"
    
    if not prompt_file.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_file}")
    
    try:
        with open(prompt_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        
        if not isinstance(data, dict):
            raise ValueError(f"Invalid prompt file format: {prompt_file}")
        
        if "prompt" not in data:
            raise ValueError(f"Prompt file missing 'prompt' key: {prompt_file}")
        
        prompt_text = data["prompt"]
        if not isinstance(prompt_text, str):
            raise ValueError(f"Prompt must be a string in: {prompt_file}")
        
        # Cache the prompt
        _prompt_cache[prompt_name] = prompt_text
        
        logger.debug(
            "prompt_loaded",
            prompt_name=prompt_name,
            prompt_file=str(prompt_file),
            version=data.get("version", "unknown"),
        )
        
        return prompt_text
    except yaml.YAMLError as e:
        raise ValueError(f"Failed to parse YAML in {prompt_file}: {e}") from e
    except Exception as e:
        logger.error(
            "prompt_load_failed",
            prompt_name=prompt_name,
            prompt_file=str(prompt_file),
            error=str(e),
            error_type=type(e).__name__,
        )
        raise


def get_system_prompt() -> str:
    """
    Get the system prompt for the agent.
    
    Returns:
        The system prompt text
    """
    return load_prompt("system_prompt")

