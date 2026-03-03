"""
Configuration management for Harpo.
"""

from dotenv import load_dotenv
from pydantic import ConfigDict
from pydantic_settings import BaseSettings

# Load environment variables from .env
load_dotenv()


class HarpoConfig(BaseSettings):
    """
    Configuration settings for Harpo, including OpenRouter API details.
    """

    model_config = ConfigDict(
        env_prefix="HARP_",
        env_file=".env",
        extra="ignore",
    )

    api_key: str = ""
    api_base_url: str = "https://openrouter.ai/api/v1"
    api_model: str = "google/gemini-flash-1.5"
