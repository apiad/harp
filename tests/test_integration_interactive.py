"""
Integration test for interactive transcription mode.
Simulates a real recording session by feeding chunks of audio.
"""

import os
import time
import wave
import numpy as np
import pytest
from fuzzywuzzy import fuzz
import string

from harp.daemon import DaemonState, HarpoDaemon
from harp.api import BatchResponse
from harp.config import HarpoConfig

GROUND_TRUTH_TXT = "tests/assets/ground_truth.txt"
GROUND_TRUTH_WAV = "tests/assets/ground_truth.wav"


def normalize_text(text: str) -> str:
    text = text.lower()
    text = text.translate(str.maketrans("", "", string.punctuation))
    return " ".join(text.split())


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.skipif(
    not os.path.exists(GROUND_TRUTH_WAV), reason="Ground truth audio not recorded yet."
)
async def test_interactive_transcription_sliding_window():
    """
    Simulates interactive mode with the new sliding-window re-transcription strategy.
    """
    # 1. Load Ground Truth
    with open(GROUND_TRUTH_TXT, "r") as f:
        original_text = f.read().strip()

    with wave.open(GROUND_TRUTH_WAV, "rb") as wf:
        n_frames = wf.getnframes()
        samplerate = wf.getframerate()
        audio_bytes = wf.readframes(n_frames)
        audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
        full_audio = audio_int16.astype(np.float32) / 32767.0

    config = HarpoConfig()
    if not config.api_key:
        pytest.fail("HARP_API_KEY not set")

    daemon = HarpoDaemon(interactive=True, interval=5.0)
    daemon.state = DaemonState.RECORDING

    # Simulation Parameters (Matching daemon.py)
    warmup_seconds = 15.0
    window_seconds = 10.0
    loop_interval = 5.0

    total_samples = len(full_audio)
    current_sample = 0

    start_time = time.time()

    print("\n[DEBUG] Starting sliding-window interactive simulation...")

    while current_sample < total_samples:
        iter_start = time.time()

        # Initial 15s buffer, then 5s steps
        if current_sample == 0:
            current_sample = int(warmup_seconds * samplerate)
        else:
            current_sample += int(loop_interval * samplerate)

        current_duration = current_sample / samplerate

        if current_sample > total_samples:
            current_sample = total_samples

        # Get rolling window (last 10 seconds)
        window_start = max(0, current_sample - int(window_seconds * samplerate))
        audio_data = full_audio[window_start:current_sample].reshape(-1, 1)

        # 4. Prompt with FULL Context (Matching daemon.py logic)
        instruction = (
            "You are a real-time transcription assistant. "
            f"So far, you have transcribed: '{daemon.current_session_text}'. "
            "The following 10 seconds of audio continues the session with some overlap. "
            "Provide the FULL, UPDATED transcription of the session so far. "
            "IMPORTANT: Make sure the existing prefix of the text stays the same or as similar as possible. "
            "Return ONLY the updated full transcription."
        )

        try:
            response = await daemon.api_client.transcribe(
                audio_data=audio_data,
                samplerate=samplerate,
                model=config.api_model,
                instruction=instruction,
                response_model=BatchResponse,
            )
            updated_full_text = daemon.typer.filter_text(response.full_text)
        except Exception as e:
            print(f"[ERROR] API call failed: {e}")
            continue

        api_latency = time.time() - iter_start

        # 5. Full Update (LCP logic is handled by type_diff in the real daemon,
        # but here we just update the state)
        daemon.current_session_text = updated_full_text

        print(
            f"[{current_duration:4.1f}s] Latency: {api_latency:.2f}s | Current Len: {len(updated_full_text)}"
        )

    total_duration = time.time() - start_time
    final_text = daemon.current_session_text

    norm_original = normalize_text(original_text)
    norm_final = normalize_text(final_text)
    similarity = fuzz.ratio(norm_original, norm_final)

    print("\n[SUMMARY]")
    print(f"Total Time: {total_duration:.2f}s")
    print(f"Final Similarity: {similarity}%")
    print(f"Final Result: {final_text[:200]}...")

    assert similarity >= 60, f"Sliding window similarity ({similarity}%) is too low."
