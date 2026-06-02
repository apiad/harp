"""End-to-end integration test (marked @pytest.mark.integration).

Drives a HarpSession + ClipboardSink against a known WAV. Asserts the
clipboard receives the final text exactly once and that no per-character
typing keystrokes are emitted.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from harp.cli.clipboard import ClipboardSink
from harp.session import HarpSession
from harp.whisper import LocalWhisperEngine
from tests.fakes import FileAudioSource

ASSET = Path(__file__).parent / "assets" / "ground_truth.wav"


@pytest.mark.integration
def test_end_to_end_paste_only() -> None:
    if not ASSET.exists():
        pytest.skip(f"missing asset {ASSET}")
    if not LocalWhisperEngine.list_local_models():
        pytest.skip("no local Whisper models — run 'harp models download base'")

    engine = LocalWhisperEngine(model_size="base", device="cpu", compute_type="int8")
    src = FileAudioSource(ASSET, chunk_ms=200)

    writes: list[bytes] = []
    snapshot = MagicMock(return_value=b"PRE")

    def write(b: bytes) -> None:
        writes.append(b)

    ctrl_v = MagicMock()
    sleep = MagicMock()

    sink = ClipboardSink(
        snapshot=snapshot,
        write=write,
        ctrl_v=ctrl_v,
        sleep=sleep,
        paste=True,
    )

    with HarpSession(audio=src, transcribe=engine.transcribe, slide_interval=0.5) as s:
        list(s.events())
        final = s.final_text

    sink.deliver(final)

    assert final.strip(), "expected non-empty transcription from asset WAV"
    assert len(writes) == 2
    assert writes[0].decode() == final
    assert writes[1] == b"PRE"
    assert ctrl_v.call_count == 1
