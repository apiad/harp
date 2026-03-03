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
async def test_interactive_transcription_stitching():
    """
    Simulates interactive mode with the new Warm-up + Contextual Overlap logic.
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

    daemon = HarpoDaemon(interactive=True, interval=1.0)
    daemon.state = DaemonState.RECORDING

    # Simulation Parameters (Matching daemon.py)
    warmup_seconds = 15.0
    window_seconds = 10.0

    chunk_step_seconds = 2.0  # Simulate an iteration every 2 seconds
    total_samples = len(full_audio)
    current_sample = 0

    intermediate_results = []
    start_time = time.time()

    print("\n[DEBUG] Starting contextual interactive simulation...")

    while current_sample < total_samples:
        iter_start = time.time()

        # Advance time
        current_sample += int(chunk_step_seconds * samplerate)
        current_duration = current_sample / samplerate

        if current_duration < warmup_seconds:
            print(f"[{current_duration:4.1f}s] Buffering...")
            continue

        # Get rolling window (last 10 seconds)
        window_start = max(0, current_sample - int(window_seconds * samplerate))
        audio_data = full_audio[window_start:current_sample].reshape(-1, 1)

        # 4. Context-Aware Prompting (Matching daemon.py logic)
        context = daemon.current_session_text[-200:]
        instruction = (
            "You are a real-time transcription assistant. "
            f"The user has already said: '...{context}'. "
            "The provided audio overlaps with the end of that text. "
            "Transcribe the audio exactly, starting from where the context ends. "
            "Return ONLY the transcription."
        )

        try:
            response = await daemon.api_client.transcribe(
                audio_data=audio_data,
                samplerate=samplerate,
                model=config.api_model,
                instruction=instruction,
                response_model=BatchResponse,
            )
            window_text = daemon.typer.filter_text(response.full_text)
        except Exception as e:
            print(f"[ERROR] API call failed: {e}")
            continue

        api_latency = time.time() - iter_start

        # 5. Fuzzy Stitching (Matching daemon.py logic)
        words_session = daemon.current_session_text.split()
        words_window = window_text.split()

        if not words_session:
            new_total_text = window_text
        else:
            best_match_idx = -1
            max_ratio = 0
            lookback = min(len(words_session), 10)

            for i in range(1, lookback + 1):
                overlap_candidate = " ".join(words_session[-i:])
                window_start_text = " ".join(words_window[: i + 2])
                ratio = fuzz.partial_ratio(
                    overlap_candidate.lower(), window_start_text.lower()
                )

                if ratio > 85 and ratio > max_ratio:
                    max_ratio = ratio
                    best_match_idx = i

            if best_match_idx != -1:
                remaining_words = words_window[best_match_idx:]
                new_total_text = (
                    daemon.current_session_text + " " + " ".join(remaining_words)
                )
            else:
                if len(words_window) > 5:
                    new_total_text = (
                        daemon.current_session_text + " " + window_text
                    ).strip()
                else:
                    new_total_text = daemon.current_session_text

        delta = new_total_text[len(daemon.current_session_text) :].strip()
        daemon.current_session_text = new_total_text

        intermediate_results.append(
            {"chunk_end_sec": current_duration, "delta": delta, "latency": api_latency}
        )

        print(
            f"[{current_duration:4.1f}s] Latency: {api_latency:.2f}s | Delta: '{delta}'"
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

    assert similarity >= 50, (
        f"Interactive stitching similarity ({similarity}%) is too low."
    )
