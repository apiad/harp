"""
OpenRouter API integration for STT.
"""

from typing import Any

from openai import OpenAI


class OpenRouterClient:
    """
    Client for interacting with OpenRouter STT models.
    """

    def __init__(
        self, api_key: str, base_url: str = "https://openrouter.ai/api/v1"
    ) -> None:
        """
        Initializes the OpenRouterClient.

        Args:
            api_key: The OpenRouter API key.
            base_url: The OpenRouter API base URL.
        """
        self.client: OpenAI = OpenAI(api_key=api_key, base_url=base_url)

    async def transcribe(self, audio_data: Any) -> str:
        """
        Sends audio data to OpenRouter for transcription.

        Args:
            audio_data: The audio payload to transcribe.

        Returns:
            The transcribed text.
        """
        # Placeholder for transcription logic using OpenRouter/OpenAI-compatible API.
        return ""
