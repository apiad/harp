"""
Integration test for interactive transcription mode.
Simulates a real recording session by feeding chunks of audio.
"""

import asyncio
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
async def test_interactive_transcription_stitching():
    """
    Simulates interactive mode by feeding audio chunks and verifying the stitched result.
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

    # 2. Setup Daemon with real API but mocked AudioStreamer
    config = HarpoConfig()
    if not config.api_key:
        pytest.fail("HARP_API_KEY not set")

    # We use a real daemon but override the audio streamer
    daemon = HarpoDaemon(interactive=True, interval=1.0)
    daemon.state = DaemonState.RECORDING

    # Mock the audio streamer to return chunks
    # We simulate the 5s rolling window
    chunk_size = samplerate * 1  # 1 second chunks
    total_samples = len(full_audio)
    current_sample = 0

    intermediate_results = []
    start_time = time.time()

    print("\n[DEBUG] Starting interactive simulation...")

    # We manually run the stitching logic similar to _interactive_loop
    # to have full control and debug capabilities.
    while current_sample < total_samples:
        iter_start = time.time()

        # Advance "clock"
        current_sample += chunk_size
        # Get rolling window (last 5 seconds)
        window_start = max(0, current_sample - (samplerate * 5))
        audio_data = full_audio[window_start:current_sample].reshape(-1, 1)

        # Call API
        try:
            response = await daemon.api_client.transcribe(
                audio_data=audio_data,
                samplerate=samplerate,
                model=config.api_model,
                instruction="Transcribe the provided audio exactly.",
                response_model=BatchResponse,
            )
            window_text = daemon.typer.filter_text(response.full_text)
        except Exception as e:
            print(f"[ERROR] API call failed: {e}")
            continue

        api_latency = time.time() - iter_start

        # Apply Stitching Logic (Copied from daemon.py for exact verification)
        words_session = daemon.current_session_text.split()

        if not words_session:
            new_total_text = window_text
        else:
            overlap_found = False
            for i in range(min(len(words_session), 5), 0, -1):
                overlap_candidate = " ".join(words_session[-i:])
                if window_text.lower().startswith(overlap_candidate.lower()):
                    remaining_words = window_text.split()[i:]
                    if remaining_words:
                        new_total_text = (
                            daemon.current_session_text + " " + " ".join(remaining_words)
                        )
                    else:
                        new_total_text = daemon.current_session_text
                    overlap_found = True
                    break

            if not overlap_found:
                new_total_text = (
                    daemon.current_session_text + " " + window_text
                ).strip()

        delta = new_total_text[len(daemon.current_session_text) :].strip()
        daemon.current_session_text = new_total_text

        intermediate_results.append(
            {
                "chunk_end_sec": current_sample / samplerate,
                "window_text": window_text,
                "delta": delta,
                "latency": api_latency,
            }
        )

        print(
            f"[{current_sample/samplerate:4.1f}s] Latency: {api_latency:.2f}s | Delta: '{delta}'"
        )

    total_duration = time.time() - start_time
    final_text = daemon.current_session_text

    # 3. Validation
    norm_original = normalize_text(original_text)
    norm_final = normalize_text(final_text)
    similarity = fuzz.ratio(norm_original, norm_final)

    print("\n[SUMMARY]")
    print(f"Total Time: {total_duration:.2f}s")
    print(f"Final Similarity: {similarity}%")
    print(f"Final Result: {final_text[:200]}...")

    # We expect a slightly lower threshold for interactive due to potential stitching artifacts
    assert similarity >= 60, f"Interactive stitching similarity ({similarity}%) is too low."

    # Analyze latency
    avg_latency = sum(r["latency"] for r in intermediate_results) / len(
        intermediate_results
    )
    print(f"Average API Latency: {avg_latency:.2f}s")
    assert avg_latency < 5.0, "API response time is too slow for interactive mode."
