"""
Configuration management for Harpo.
"""

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Load environment variables from .env
load_dotenv()


class HarpoConfig(BaseSettings):
    """
    Configuration settings for Harpo, including OpenRouter API details.
    """

    api_key: str = ""
    api_base_url: str = "https://openrouter.ai/api/v1"
    api_model: str = "openai/gpt-4o-audio-preview"

    class Config:
        """
        Configuration for the Pydantic settings model.
        """

        env_prefix: str = "HARP_"
        env_file: str = ".env"
