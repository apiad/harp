"""
End-to-end integration test using a real voice recording.
"""

import os
import wave
import numpy as np
import pytest
from fuzzywuzzy import fuzz
import string

from harp.api import OpenRouterClient, BatchResponse
from harp.config import HarpConfig

GROUND_TRUTH_TXT = "tests/assets/ground_truth.txt"
GROUND_TRUTH_WAV = "tests/assets/ground_truth.wav"


def normalize_text(text: str) -> str:
    """
    Lowercase, remove punctuation and extra whitespace.
    """
    text = text.lower()
    # Remove punctuation
    text = text.translate(str.maketrans("", "", string.punctuation))
    # Normalize whitespace
    return " ".join(text.split())


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.skipif(
    not os.path.exists(GROUND_TRUTH_WAV), reason="Ground truth audio not recorded yet."
)
async def test_transcription_accuracy():
    """
    Verifies that the live API transcription matches the ground truth text.
    """
    # 1. Load Ground Truth Text
    with open(GROUND_TRUTH_TXT, "r") as f:
        original_text = f.read().strip()

    # 2. Load Ground Truth Audio
    with wave.open(GROUND_TRUTH_WAV, "rb") as wf:
        n_frames = wf.getnframes()
        samplerate = wf.getframerate()
        audio_bytes = wf.readframes(n_frames)
        # Convert back to float32
        audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
        audio_data = audio_int16.astype(np.float32) / 32767.0

    # 3. Transcribe via Live API
    config = HarpConfig()
    if not config.api_key:
        pytest.fail("HARP_API_KEY not set in environment or .env")

    client = OpenRouterClient(api_key=config.api_key, base_url=config.api_base_url)

    response = await client.transcribe(
        audio_data=audio_data,
        samplerate=samplerate,
        model=config.api_model,
        instruction="Transcribe this audio EXACTLY as spoken. Do NOT paraphrase. Do NOT summarize. Output every single word precisely.",
        response_model=BatchResponse,
    )

    transcribed_text = response.full_text

    # 4. Compare
    norm_original = normalize_text(original_text)
    norm_transcribed = normalize_text(transcribed_text)

    similarity = fuzz.ratio(norm_original, norm_transcribed)

    print(f"\nSimilarity Score: {similarity}%")
    print(f"Original: {original_text[:100]}...")
    print(f"Transcribed: {transcribed_text[:100]}...")

    assert similarity >= 95, (
        f"Transcription similarity ({similarity}%) is below 95% threshold."
    )
