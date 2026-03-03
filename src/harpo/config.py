"""
Configuration management for Harpo.
"""

from pydantic_settings import BaseSettings


class HarpoConfig(BaseSettings):
    """
    Configuration settings for Harpo, including OpenRouter API details.
    """

    openrouter_api_key: str = ""
    stt_model: str = "openai/whisper-large-v3"

    class Config:
        """
        Configuration for the Pydantic settings model.
        """

        env_prefix: str = "HARPO_"
        env_file: str = ".env"
