"""
OpenRouter API integration for STT using Chat Completions with Audio Input.
"""

import base64
import io
import wave

import numpy as np
from openai import AsyncOpenAI


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
        self, audio_data: np.ndarray, samplerate: int, model: str
    ) -> str:
        """
        Sends audio data to OpenRouter for transcription using Chat Completions.

        Args:
            audio_data: The audio payload as a float32 numpy array.
            samplerate: The sample rate of the audio data.
            model: The multimodal model to use (e.g., openai/gpt-4o-audio-preview).

        Returns:
            The transcribed text.
        """
        if audio_data.size == 0:
            return ""

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

        # 4. Call OpenRouter Chat Completions API
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Transcribe this audio exactly."},
                            {
                                "type": "input_audio",
                                "input_audio": {"data": base64_audio, "format": "wav"},
                            },
                        ],
                    }
                ],
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            print(f"Transcription error: {e}")
            return f"Error: {e}"
