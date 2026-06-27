"""
Configuration management for Harp.
"""

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

    # Local STT (Whisper) Settings
    local_model: str = Field(
        default="base", description="Local Whisper model to use (e.g., base, small)"
    )
    local_device: str = Field(
        default="auto", description="Device for local STT (cpu, cuda, auto)"
    )
    local_compute_type: str = Field(
        default="default",
        description="Compute type for local STT (int8, float16, float32, default)",
    )
    local_language: Optional[str] = Field(
        default=None, description="Language code for local STT (e.g., 'en', 'es')"
    )

    # Output Mode
    paste: bool = Field(
        default=True,
        description="Auto-paste (Ctrl+V) the final transcription into the focused window",
    )

    # STT Behavior (VAD-segmented streaming)
    stream_warmup: float = Field(
        default=10.0, description="Seconds buffered before entering chunked mode"
    )
    stream_silence_threshold: float = Field(
        default=0.5, description="Trailing silence (s) that finalizes a chunk"
    )
    stream_max_segment: float = Field(
        default=25.0, description="Force-cut length (s) when no pause is found"
    )
    stream_vad: bool = Field(
        default=True, description="Use Silero VAD for chunk boundaries"
    )
    stream_transient: bool = Field(
        default=False,
        description="Emit a live transient preview (re-decodes the in-progress "
        "chunk every slide — costs ~2-4x compute; off keeps streaming real-time)",
    )
    stream_beam_size: int = Field(
        default=1, description="Beam size for streaming decodes (1 = fastest)"
    )
    # NOTE: stream_slide_interval must be tuned per model/device on a host
    # with a real microphone. Default below is a conservative guess; see
    # README / CHANGELOG for tuning guidance.
    stream_slide_interval: float = Field(
        default=1.0,
        description="Seconds between transient-preview re-decode passes",
    )

    # UI/Behavior
    toggle: bool = Field(
        default=False, description="Toggle recording state on keypress"
    )
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
