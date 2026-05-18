"""
End-to-end integration test using a real voice recording and local Whisper.
"""

import os
import wave
import string
import numpy as np
import pytest
from fuzzywuzzy import fuzz

from harp.whisper import LocalWhisperEngine

GROUND_TRUTH_TXT = "tests/assets/ground_truth.txt"
GROUND_TRUTH_WAV = "tests/assets/ground_truth.wav"


def normalize_text(text: str) -> str:
    """
    Lowercase, remove punctuation and extra whitespace.
    """
    text = text.lower()
    text = text.translate(str.maketrans("", "", string.punctuation))
    return " ".join(text.split())


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.skipif(
    not os.path.exists(GROUND_TRUTH_WAV), reason="Ground truth audio not recorded yet."
)
async def test_local_transcription_accuracy():
    """
    Verifies that the local Whisper transcription matches the ground truth text.
    """
    # 1. Load Ground Truth Text
    with open(GROUND_TRUTH_TXT, "r") as f:
        original_text = f.read().strip()

    # 2. Load Ground Truth Audio
    with wave.open(GROUND_TRUTH_WAV, "rb") as wf:
        n_frames = wf.getnframes()
        audio_bytes = wf.readframes(n_frames)
        audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
        audio_data = audio_int16.astype(np.float32) / 32767.0

    # 3. Transcribe via Local Whisper

    # Use 'base' for gold standard accuracy
    engine = LocalWhisperEngine(model_size="base", device="cpu", compute_type="int8")

    # Check if model exists, if not, skip or use tiny
    if not LocalWhisperEngine.list_local_models():
        # Download tiny for CI testing if needed, or skip
        # For this test, we assume the user has at least one model if they run integration tests
        pytest.skip(
            "No local Whisper models found. Run 'harp models download base' first."
        )

    import time

    start_time = time.time()
    transcribed_text = engine.transcribe(audio_data)
    duration = time.time() - start_time

    # 4. Compare
    norm_original = normalize_text(original_text)
    norm_transcribed = normalize_text(transcribed_text)

    similarity = fuzz.ratio(norm_original, norm_transcribed)

    print(f"\nSimilarity Score: {similarity}%")
    print(f"Transcription Time: {duration:.2f}s")
    print(f"Original: {original_text[:100]}...")
    print(f"Transcribed: {transcribed_text[:100]}...")

    # Local Whisper 'base' should be very accurate for clear audio
    assert similarity >= 90, (
        f"Transcription similarity ({similarity}%) is below 90% threshold."
    )


@pytest.mark.integration
@pytest.mark.skip(
    reason=(
        "Streaming end-to-end with tiny CPU decode runs ~70 re-decodes of a "
        "30s rolling window for a 70s clip and exceeds practical CPU timeouts "
        "in this environment. Enable manually on a mic/GPU-equipped host."
    )
)
@pytest.mark.skipif(
    not os.path.exists(GROUND_TRUTH_WAV), reason="Ground truth audio not recorded yet."
)
def test_streaming_transcriber_end_to_end():
    """
    Feeds the ground-truth WAV through a real StreamingTranscriber in ~1s
    slices and asserts the finalized text fuzzy-matches the ground truth.
    """
    from harp.streaming import StreamingTranscriber

    if not LocalWhisperEngine.list_local_models():
        pytest.skip(
            "No local Whisper models found. Run 'harp models download tiny' first."
        )

    with open(GROUND_TRUTH_TXT, "r") as f:
        original_text = f.read().strip()

    with wave.open(GROUND_TRUTH_WAV, "rb") as wf:
        sr = wf.getframerate()
        n_frames = wf.getnframes()
        audio_bytes = wf.readframes(n_frames)
        audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
        audio_data = audio_int16.astype(np.float32) / 32767.0

    engine = LocalWhisperEngine(model_size="tiny", device="cpu", compute_type="int8")
    st = StreamingTranscriber(transcribe=engine.transcribe, samplerate=sr)

    slice_samples = sr
    for start in range(0, audio_data.shape[0], slice_samples):
        st.feed(audio_data[start : start + slice_samples])
        st.step()
    final = st.finalize()

    similarity = fuzz.ratio(normalize_text(original_text), normalize_text(final.committed))
    print(f"\nStreaming similarity: {similarity}%")
    assert similarity > 80, (
        f"Streaming transcription similarity ({similarity}%) is below 80% threshold."
    )
