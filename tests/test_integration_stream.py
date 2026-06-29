"""End-to-end streaming integration over the real fixture.

Exercises the full engine: FileSource -> Silero VAD -> StreamingTranscriber
-> HarpSession, with a real faster-whisper `base` model. Marked slow because
it loads two models and decodes ~73s of audio.
"""

from pathlib import Path

import pytest

from harp.audio import FileSource
from harp.events import TranscriptEvent
from harp.session import HarpSession
from harp.vad import SileroDetector
from harp.whisper import LocalWhisperEngine

FIXTURE = Path(__file__).parent / "assets" / "ground_truth.wav"


@pytest.mark.slow
def test_long_audio_streams_in_chunks_and_covers_text():
    engine = LocalWhisperEngine(model_size="base")
    src = FileSource(FIXTURE)
    with HarpSession(
        audio=src,
        transcribe=engine.transcribe,
        transcribe_segments=engine.transcribe_segments,
        detector=SileroDetector(),
        slide_interval=2.0,  # realistic transient cadence; keeps the test bounded
        warmup=10.0,
        language="en",
    ) as session:
        events = list(session.events())
        final = session.final_text.lower()

    # All events are the two-tier type; a terminal is_final lands last.
    assert all(isinstance(e, TranscriptEvent) for e in events)
    assert events[-1].is_final is True

    # committed is append-only across the stream (ignoring transient previews).
    committed_seq = [e.committed for e in events if e.committed]
    for earlier, later in zip(committed_seq, committed_seq[1:]):
        assert later.startswith(earlier)

    # The full ~73s transcribed (not just a warm-up window): sentences from the
    # start, middle, and near-end all appear.
    assert "existence is not a static" in final
    assert "human condition" in final
    assert "continue to dance" in final
    # More than one chunk was finalized (long audio => multiple boundaries).
    assert len(committed_seq) >= 3
