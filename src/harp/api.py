"""
OpenRouter API integration for STT using Chat Completions with Audio Input.
"""

import base64
import io
import wave
from typing import Type, TypeVar

import numpy as np
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

T = TypeVar("T", bound=BaseModel)


class BatchResponse(BaseModel):
    """
    Structured response for full transcription.
    """

    full_text: str = Field(default="", description="The complete transcribed text.")


class CommandResponse(BaseModel):
    """
    Structured response for command execution requests.
    """

    action: str = Field(description="The action to perform.")
    parameters: dict = Field(default_factory=dict, description="Action parameters.")


class OpenRouterClient:
    """
    Client for interacting with OpenRouter models that support audio input.
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
        self.client: AsyncOpenAI = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def transcribe(
        self,
        audio_data: np.ndarray,
        samplerate: int,
        model: str,
        instruction: str = "Transcribe this audio exactly.",
        response_model: Type[T] = BatchResponse,
    ) -> T:
        """
        Sends audio data to OpenRouter for transcription using Chat Completions with Structured Output.

        Args:
            audio_data: The audio payload as a float32 numpy array.
            samplerate: The sample rate of the audio data.
            model: The multimodal model to use (e.g., openai/gpt-4o-audio-preview).
            instruction: The instruction to give to the model.
            response_model: The Pydantic model to parse the response into.

        Returns:
            The parsed Pydantic model.
        """
        if audio_data.size == 0:
            return response_model()

        # 1. Convert float32 [-1.0, 1.0] to int16
        audio_int16 = (np.clip(audio_data, -1.0, 1.0) * 32767).astype(np.int16)

        # 2. Write to in-memory WAV buffer
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 2 bytes for int16
            wf.setframerate(samplerate)
            wf.writeframes(audio_int16.tobytes())

        buffer.seek(0)
        # 3. Encode to Base64
        base64_audio = base64.b64encode(buffer.read()).decode("utf-8")

        # 4. Call OpenRouter Chat Completions API with Structured Output
        try:
            # We use the standard 'parse' method from openai-python for Pydantic support
            completion = await self.client.beta.chat.completions.parse(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": instruction},
                            {
                                "type": "input_audio",
                                "input_audio": {"data": base64_audio, "format": "wav"},
                            },
                        ],
                    }
                ],
                # Pass the Pydantic model directly
                response_format=response_model,
            )
            parsed = completion.choices[0].message.parsed
            if parsed is None:
                raise ValueError("Failed to parse response into model.")
            return parsed
        except Exception as e:
            print(f"Transcription error: {e}")
            raise e
