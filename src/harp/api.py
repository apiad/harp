"""
LLM integration for post-processing and command mode.
"""

from openai import AsyncOpenAI


class LLMClient:
    """
    Client for interacting with OpenAI-compatible LLM APIs.
    """

    def __init__(
        self, api_key: str, base_url: str = "https://openrouter.ai/api/v1"
    ) -> None:
        """
        Initializes the LLMClient.

        Args:
            api_key: The API key.
            base_url: The API base URL.
        """
        self.client: AsyncOpenAI = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def process_text(
        self,
        text: str,
        instruction: str,
        model: str,
    ) -> str:
        """
        Sends text to the LLM for post-processing or command execution.

        Args:
            text: The transcribed text.
            instruction: The instruction to give to the model.
            model: The LLM model to use.

        Returns:
            The processed text from the LLM.
        """
        if not text:
            return ""

        try:
            completion = await self.client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": instruction,
                    },
                    {
                        "role": "user",
                        "content": text,
                    },
                ],
            )
            return completion.choices[0].message.content or ""
        except Exception as e:
            print(f"LLM processing error: {e}")
            raise e
