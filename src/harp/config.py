"""
Configuration management for Harp.
"""

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import ConfigDict, Field
from pydantic_settings import BaseSettings


class HarpConfig(BaseSettings):
    """
    Configuration settings for Harp, including API details and output modes.
    """

    model_config = ConfigDict(
        env_prefix="HARP_",
        env_file=".env",
        extra="ignore",
    )

    # API Settings
    api_key: str = Field(default="", description="OpenRouter API key")
    api_base_url: str = Field(
        default="https://openrouter.ai/api/v1", description="API base URL"
    )
    api_model: str = Field(default="google/gemini-2.0-flash", description="AI model to use")

    # Output Modes
    type_result: bool = Field(default=False, alias="type", description="Type the result")
    copy_result: bool = Field(
        default=False, alias="copy", description="Copy the result to clipboard"
    )
    send_clipboard: int = Field(
        default=0, description="Tokens to send from clipboard in command mode"
    )

    # Prompts
    transcribe_prompt: str = Field(
        default="Transcribe this audio exactly.", description="Prompt for transcription"
    )
    command_prompt: str = Field(
        default=(
            "Listen to the following audio. It contains a command or instruction. "
            "Execute the command or follow the instruction and provide ONLY the result. "
            "Do NOT transcribe the audio, do NOT acknowledge the request, just output the final result."
        ),
        description="Prompt for command mode",
    )

    # UI/Behavior
    toggle: bool = Field(default=False, description="Toggle recording state on keypress")
    full_mode: bool = Field(
        default=False, description="Type all characters including symbols"
    )
    device: Optional[str] = Field(
        default=None, description="Path or name of the device to grab"
    )


def find_config_file() -> Optional[Path]:
    """
    Searches for .harp.yaml from the current directory up to the user's home directory.
    Returns the path to the first one found, or None.
    """
    current_dir = Path.cwd().resolve()
    home_dir = Path.home().resolve()

    # Search upwards
    for parent in [current_dir] + list(current_dir.parents):
        config_path = parent / ".harp.yaml"
        if config_path.exists() and config_path.is_file():
            return config_path

        # Stop if we've reached the home directory or gone beyond it
        if parent == home_dir:
            break

    return None


def load_config(overrides: Optional[dict] = None) -> HarpConfig:
    """
    Loads configuration from .harp.yaml (if found) and merges with environment
    variables and provided overrides.

    Args:
        overrides: Dictionary of values to override (e.g., from CLI flags).

    Returns:
        A resolved HarpConfig instance.
    """
    config_data = {}

    config_path = find_config_file()
    if config_path:
        try:
            with open(config_path, "r") as f:
                yaml_data = yaml.safe_load(f)
                if isinstance(yaml_data, dict):
                    config_data = yaml_data
        except Exception:
            # If loading fails, we just fall back to defaults/env
            pass

    # Merge overrides into config_data
    if overrides:
        # Filter out None values from overrides so they don't overwrite config file values
        filtered_overrides = {k: v for k, v in overrides.items() if v is not None}
        config_data.update(filtered_overrides)

    return HarpConfig(**config_data)
