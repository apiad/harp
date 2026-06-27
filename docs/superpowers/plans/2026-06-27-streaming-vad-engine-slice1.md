# Streaming VAD Engine — Slice 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the thinnest end-to-end path of the VAD-segmented streaming
engine: decode a file, stream `TranscriptEvent`s (committed + transient),
finalize each speech chunk exactly once at silence boundaries, and print the
result via `harp transcribe <file>`.

**Architecture:** A pure, dependency-injected `StreamingTranscriber` accumulates
audio, emits a transient preview during a warm-up window, then past warm-up
finalizes a chunk whenever a Silero VAD detector reports trailing silence —
decoding that chunk once, appending to an append-only `committed` string, and
dropping its audio so it is never re-decoded. A `FileSource` feeds it, and a
`harp transcribe` CLI verb renders committed text "in the dark" and transient
"in the light."

**Tech Stack:** Python 3.12+, `faster-whisper` (bundles Silero VAD via
`faster_whisper.vad` and audio decode via `faster_whisper.audio.decode_audio`),
`numpy`, `typer`, `rich`, `pytest`.

## Global Constraints

- Python 3.12+.
- No new heavy dependencies: Silero VAD and `decode_audio` already ship inside
  `faster-whisper` (already a dependency).
- The engine (`streaming.py`) stays pure and I/O-free: it receives a
  `transcribe` callable and a `SpeechDetector` — it never imports a model.
- Tests are written and run inline (never delegated).
- Commit directly to `main` (harp convention). Conventional-commit messages,
  ending with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- `transcribe` callable signature is fixed:
  `Callable[[np.ndarray, Optional[str], Optional[str]], str]`
  = `(audio_float32_16k_mono, initial_prompt, language) -> text`.
- Audio is 16 kHz mono float32 inside the engine; `int16` PCM bytes only at the
  `AudioSource` boundary.

---

### Task 1: `TranscriptEvent` two-tier event

**Files:**
- Modify: `src/harp/events.py`
- Test: `tests/test_events.py`

**Interfaces:**
- Produces: `TranscriptEvent(committed: str, transient: str, is_final: bool, ts: float)`
  with property `text -> str` returning `f"{committed} {transient}".strip()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_events.py
from harp.events import TranscriptEvent


def test_text_joins_committed_and_transient():
    ev = TranscriptEvent(committed="hello world", transient="how are", is_final=False, ts=1.0)
    assert ev.text == "hello world how are"


def test_text_strips_when_transient_empty():
    ev = TranscriptEvent(committed="hello world", transient="", is_final=True, ts=2.0)
    assert ev.text == "hello world"


def test_event_is_frozen():
    ev = TranscriptEvent(committed="a", transient="b", is_final=False, ts=0.0)
    import dataclasses, pytest
    with pytest.raises(dataclasses.FrozenInstanceError):
        ev.committed = "x"  # type: ignore[misc]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_events.py -v`
Expected: FAIL with `ImportError: cannot import name 'TranscriptEvent'`

- [ ] **Step 3: Replace `CommitEvent` with `TranscriptEvent`**

```python
# src/harp/events.py
"""Public event types yielded by HarpSession."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptEvent:
    """Two-tier transcription snapshot.

    ``committed`` is the cumulative finalized text: append-only, never revised.
    ``transient`` is the current hypothesis of the in-progress segment; it may
    be rewritten or emptied between events. Consumers render committed text
    "in the dark" and transient "in the light".
    """

    committed: str
    transient: str
    is_final: bool
    ts: float

    @property
    def text(self) -> str:
        return f"{self.committed} {self.transient}".strip()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_events.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/harp/events.py tests/test_events.py
git commit -m "feat(events): two-tier TranscriptEvent (committed + transient)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: `SpeechDetector` protocol + `SileroDetector`

**Files:**
- Create: `src/harp/vad.py`
- Test: `tests/test_vad.py`

**Interfaces:**
- Produces:
  - `SpeechDetector` Protocol with
    `speech_segments(audio: np.ndarray) -> list[tuple[int, int]]`
    (sample-index `(start, end)` pairs over a 16 kHz float32 array).
  - `SileroDetector(threshold: float = 0.5, min_silence_ms: int = 300)`
    implementing it via `faster_whisper.vad.get_speech_timestamps`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_vad.py
import numpy as np
import pytest

from harp.vad import SpeechDetector, SileroDetector


def test_protocol_runtime_checkable():
    class Dummy:
        def speech_segments(self, audio):
            return [(0, 10)]
    assert isinstance(Dummy(), SpeechDetector)


@pytest.mark.slow
def test_silero_finds_no_speech_in_silence():
    det = SileroDetector()
    segs = det.speech_segments(np.zeros(16000, dtype=np.float32))
    assert segs == []


@pytest.mark.slow
def test_silero_returns_sample_index_tuples():
    det = SileroDetector()
    # 0.5s silence, 1s tone-ish noise, 0.5s silence
    rng = np.random.default_rng(0)
    audio = np.concatenate([
        np.zeros(8000, dtype=np.float32),
        (rng.standard_normal(16000).astype(np.float32) * 0.3),
        np.zeros(8000, dtype=np.float32),
    ])
    segs = det.speech_segments(audio)
    assert all(isinstance(s, tuple) and len(s) == 2 for s in segs)
    assert all(0 <= a < b <= audio.shape[0] for a, b in segs)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_vad.py -v`
Expected: FAIL with `ImportError: cannot import name 'SpeechDetector'`

- [ ] **Step 3: Implement `vad.py`**

```python
# src/harp/vad.py
"""Streaming voice-activity detection over 16 kHz float32 audio."""

from __future__ import annotations

from typing import List, Protocol, Tuple, runtime_checkable

import numpy as np


@runtime_checkable
class SpeechDetector(Protocol):
    """Returns speech spans as (start_sample, end_sample) tuples."""

    def speech_segments(self, audio: np.ndarray) -> List[Tuple[int, int]]: ...


class SileroDetector:
    """SpeechDetector backed by the Silero VAD bundled with faster-whisper."""

    def __init__(self, threshold: float = 0.5, min_silence_ms: int = 300) -> None:
        from faster_whisper.vad import VadOptions

        self._options = VadOptions(
            threshold=threshold,
            min_silence_duration_ms=min_silence_ms,
        )
        self._sr = 16000

    def speech_segments(self, audio: np.ndarray) -> List[Tuple[int, int]]:
        from faster_whisper.vad import get_speech_timestamps

        if audio.size == 0:
            return []
        audio = np.ascontiguousarray(audio, dtype=np.float32)
        spans = get_speech_timestamps(
            audio, vad_options=self._options, sampling_rate=self._sr
        )
        return [(int(s["start"]), int(s["end"])) for s in spans]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_vad.py -v`
Expected: PASS (the two `slow` tests load the Silero model on first run)

- [ ] **Step 5: Register the `slow` marker (if not present) and commit**

Check `pyproject.toml` `[tool.pytest.ini_options]` for a `markers` entry; add
`"slow: loads a model / slower integration test"` if missing.

```bash
git add src/harp/vad.py tests/test_vad.py pyproject.toml
git commit -m "feat(vad): SpeechDetector protocol + Silero implementation

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Engine — warm-up + transient preview + finalize (no VAD cuts yet)

**Files:**
- Modify: `src/harp/streaming.py` (full rewrite of `StreamingTranscriber`)
- Test: `tests/test_streaming.py` (replace the LocalAgreement-era tests)

**Interfaces:**
- Consumes: `TranscribeFn = Callable[[np.ndarray, Optional[str], Optional[str]], str]`;
  `SpeechDetector` from `harp.vad`.
- Produces:
  - `TranscriptState(committed: str, transient: str)` with `full` property.
  - `StreamingTranscriber(transcribe, detector, samplerate=16000, warmup=10.0,
    silence_threshold=0.5, max_segment=25.0, language=None)` with methods
    `feed(pcm: np.ndarray) -> None`, `step() -> TranscriptState`,
    `finalize() -> TranscriptState`.

This task implements only warm-up behaviour and finalize; VAD cuts land in
Task 4 and force-cut in Task 5. The detector is accepted now but unused until
Task 4 (so the constructor signature is stable across tasks).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_streaming.py
import numpy as np

from harp.streaming import StreamingTranscriber, TranscriptState


def _silence(seconds, sr=16000):
    return np.zeros(int(seconds * sr), dtype=np.float32)


class FakeTranscribe:
    """Returns a fixed word count proportional to buffer seconds."""

    def __init__(self):
        self.calls = []  # records buffer lengths it was asked to decode

    def __call__(self, audio, prompt, language):
        self.calls.append(audio.shape[0])
        words = max(1, audio.shape[0] // 16000)  # ~one word per second
        return " ".join(f"w{i}" for i in range(words))


class NoSpeech:
    def speech_segments(self, audio):
        return []


def test_state_full_joins():
    assert TranscriptState("a b", "c").full == "a b c"


def test_warmup_emits_transient_not_committed():
    tx = FakeTranscribe()
    st = StreamingTranscriber(tx, NoSpeech(), warmup=10.0)
    st.feed(_silence(3))
    state = st.step()
    assert state.committed == ""
    assert state.transient != ""  # speculative decode during warm-up


def test_finalize_commits_once_for_short_input():
    tx = FakeTranscribe()
    st = StreamingTranscriber(tx, NoSpeech(), warmup=10.0)
    st.feed(_silence(4))
    st.step()
    final = st.finalize()
    assert final.committed != ""
    assert final.transient == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_streaming.py -v`
Expected: FAIL — new constructor/attributes don't exist yet.

- [ ] **Step 3: Rewrite `streaming.py`**

```python
# src/harp/streaming.py
"""Pure, I/O-free VAD-segmented streaming transcription core."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

import numpy as np

TranscribeFn = Callable[[np.ndarray, Optional[str], Optional[str]], str]


@dataclass(frozen=True)
class TranscriptState:
    """Immutable snapshot: committed is append-only; transient may change."""

    committed: str
    transient: str

    @property
    def full(self) -> str:
        return f"{self.committed} {self.transient}".strip()


class StreamingTranscriber:
    """Accumulates audio, previews a transient during a warm-up window, then
    finalizes whole speech chunks at VAD silence boundaries (Task 4) or a
    force-cut (Task 5). Finalized audio is dropped and never re-decoded."""

    def __init__(
        self,
        transcribe: TranscribeFn,
        detector,  # harp.vad.SpeechDetector
        samplerate: int = 16000,
        warmup: float = 10.0,
        silence_threshold: float = 0.5,
        max_segment: float = 25.0,
        language: Optional[str] = None,
    ) -> None:
        self._transcribe = transcribe
        self._detector = detector
        self._sr = samplerate
        self._warmup = warmup
        self._silence = silence_threshold
        self._max_segment = max_segment
        self._language = language
        self._active = np.zeros(0, dtype=np.float32)
        self._committed = ""

    # ---- input ----

    def feed(self, pcm: np.ndarray) -> None:
        self._active = np.concatenate(
            [self._active, np.asarray(pcm, dtype=np.float32).flatten()]
        )

    # ---- helpers ----

    def _seconds(self) -> float:
        return self._active.shape[0] / self._sr

    def _decode(self, audio: np.ndarray) -> str:
        if audio.size == 0:
            return ""
        prompt = self._committed[-200:] or None
        return self._transcribe(audio, prompt, self._language).strip()

    def _commit_prefix(self, end_sample: int) -> None:
        """Decode active[:end_sample] once, append to committed, drop it."""
        chunk = self._active[:end_sample]
        text = self._decode(chunk)
        if text:
            self._committed = f"{self._committed} {text}".strip()
        self._active = self._active[end_sample:]

    # ---- stepping (Task 4/5 extend _maybe_finalize) ----

    def step(self) -> TranscriptState:
        if self._active.size == 0:
            return TranscriptState(self._committed, "")
        if self._seconds() < self._warmup:
            return TranscriptState(self._committed, self._decode(self._active))
        cut = self._maybe_finalize()
        if cut:
            return TranscriptState(self._committed, "")
        return TranscriptState(self._committed, self._decode(self._active))

    def _maybe_finalize(self) -> bool:
        """Return True if a chunk was finalized this step. Extended in Task 4/5."""
        return False

    def finalize(self) -> TranscriptState:
        if self._active.size > 0:
            self._commit_prefix(self._active.shape[0])
        return TranscriptState(self._committed, "")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_streaming.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/harp/streaming.py tests/test_streaming.py
git commit -m "feat(streaming)!: VAD-segmented engine skeleton (warm-up + finalize)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: VAD boundary finalization + audio drop

**Files:**
- Modify: `src/harp/streaming.py` (`_maybe_finalize`)
- Test: `tests/test_streaming.py` (add cases)

**Interfaces:**
- Consumes: `SpeechDetector.speech_segments(audio) -> list[tuple[int, int]]`.
- Produces: same `StreamingTranscriber` API; `_maybe_finalize` now cuts at the
  end of the last speech segment when trailing silence ≥ `silence_threshold`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_streaming.py  (append)

class ScriptedSpeech:
    """Reports a single speech span ending `trailing_silence_s` before buffer end."""

    def __init__(self, trailing_silence_s, sr=16000):
        self._gap = int(trailing_silence_s * sr)
        self._sr = sr

    def speech_segments(self, audio):
        n = audio.shape[0]
        end = n - self._gap
        if end <= 0:
            return []
        return [(0, end)]


def test_vad_boundary_commits_and_drops_audio():
    tx = FakeTranscribe()
    # 12s buffer (past 10s warmup), last 1s is trailing silence -> boundary.
    st = StreamingTranscriber(
        tx, ScriptedSpeech(trailing_silence_s=1.0), warmup=10.0, silence_threshold=0.5
    )
    st.feed(_silence(12))
    state = st.step()
    assert state.committed != ""          # a chunk was finalized
    assert state.transient == ""
    # active buffer was trimmed to the ~1s trailing tail (<= 2s of samples)
    assert st._active.shape[0] <= 2 * 16000


def test_no_boundary_when_still_speaking():
    tx = FakeTranscribe()
    # trailing silence 0.1s < threshold 0.5s -> no cut, transient only.
    st = StreamingTranscriber(
        tx, ScriptedSpeech(trailing_silence_s=0.1), warmup=10.0, silence_threshold=0.5
    )
    st.feed(_silence(12))
    state = st.step()
    assert state.committed == ""
    assert state.transient != ""


def test_committed_is_append_only_across_two_chunks():
    tx = FakeTranscribe()
    st = StreamingTranscriber(
        tx, ScriptedSpeech(trailing_silence_s=1.0), warmup=10.0, silence_threshold=0.5
    )
    st.feed(_silence(12))
    first = st.step().committed
    st.feed(_silence(12))
    second = st.step().committed
    assert second.startswith(first)       # never rewritten
    assert len(second) > len(first)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_streaming.py -k vad_boundary or append -v`
Expected: FAIL — `_maybe_finalize` still returns False, so committed stays "".

- [ ] **Step 3: Implement `_maybe_finalize` (VAD branch)**

```python
# src/harp/streaming.py  — replace _maybe_finalize
    def _maybe_finalize(self) -> bool:
        segments: List[Tuple[int, int]] = self._detector.speech_segments(self._active)
        if segments:
            last_end = segments[-1][1]
            trailing = self._active.shape[0] - last_end
            if trailing >= int(self._silence * self._sr) and last_end > 0:
                self._commit_prefix(last_end)
                return True
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_streaming.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add src/harp/streaming.py tests/test_streaming.py
git commit -m "feat(streaming): finalize chunks at VAD trailing-silence boundaries

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Force-cut at `max_segment` (no-pause fallback)

**Files:**
- Modify: `src/harp/streaming.py` (`_maybe_finalize`)
- Test: `tests/test_streaming.py` (add case)

**Interfaces:**
- Produces: same API; when the active buffer exceeds `max_segment` and no VAD
  boundary fired, finalize the first `max_segment` seconds anyway (bounded cost).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_streaming.py  (append)

def test_force_cut_when_no_silence_exceeds_max_segment():
    tx = FakeTranscribe()
    # No trailing silence ever; buffer 30s > max_segment 25s -> force cut.
    st = StreamingTranscriber(
        tx, ScriptedSpeech(trailing_silence_s=0.0), warmup=10.0,
        silence_threshold=0.5, max_segment=25.0,
    )
    st.feed(_silence(30))
    state = st.step()
    assert state.committed != ""                     # forced finalize
    # dropped the first 25s, ~5s remains
    assert st._active.shape[0] <= 6 * 16000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_streaming.py::test_force_cut_when_no_silence_exceeds_max_segment -v`
Expected: FAIL — committed stays "" (no force-cut yet).

- [ ] **Step 3: Extend `_maybe_finalize` with the force-cut branch**

```python
# src/harp/streaming.py  — _maybe_finalize, after the VAD branch, before `return False`
        if self._seconds() > self._max_segment:
            self._commit_prefix(int(self._max_segment * self._sr))
            return True
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_streaming.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add src/harp/streaming.py tests/test_streaming.py
git commit -m "feat(streaming): force-cut at max_segment for pause-less speech

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: `FileSource` audio source

**Files:**
- Modify: `src/harp/audio.py`
- Test: `tests/test_audio_file.py`

**Interfaces:**
- Produces: `FileSource(path: str | Path, block_ms: int = 100)` implementing the
  existing `AudioSource` Protocol (`sample_rate: int`, `channels: int`,
  `frames() -> Iterable[bytes]`, `close() -> None`). Yields int16 PCM mono
  bytes at 16 kHz.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_audio_file.py
import wave
from pathlib import Path

import numpy as np

from harp.audio import AudioSource, FileSource


def _write_wav(path: Path, seconds=1.0, sr=16000):
    data = (np.zeros(int(seconds * sr)) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data.tobytes())


def test_filesource_is_audiosource(tmp_path):
    p = tmp_path / "a.wav"
    _write_wav(p)
    src = FileSource(p)
    assert isinstance(src, AudioSource)
    assert src.sample_rate == 16000
    assert src.channels == 1


def test_filesource_yields_int16_frames_covering_duration(tmp_path):
    p = tmp_path / "a.wav"
    _write_wav(p, seconds=1.0)
    src = FileSource(p, block_ms=100)
    total = b"".join(src.frames())
    samples = np.frombuffer(total, dtype=np.int16)
    # ~1s at 16kHz, allow rounding on the last block
    assert abs(samples.shape[0] - 16000) <= 1600


def test_filesource_missing_file_raises(tmp_path):
    import pytest
    with pytest.raises((FileNotFoundError, OSError)):
        list(FileSource(tmp_path / "nope.wav").frames())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_audio_file.py -v`
Expected: FAIL with `ImportError: cannot import name 'FileSource'`

- [ ] **Step 3: Implement `FileSource` in `audio.py`**

```python
# src/harp/audio.py  — append
from pathlib import Path
from typing import Iterable, Union

import numpy as np


class FileSource:
    """Decodes an audio file to 16 kHz mono int16 PCM frames.

    Uses faster-whisper's bundled decoder (PyAV), so any ffmpeg-readable
    container works (wav, m4a, mp3, ...).
    """

    sample_rate: int
    channels: int

    def __init__(self, path: Union[str, Path], block_ms: int = 100) -> None:
        self.sample_rate = 16000
        self.channels = 1
        self._path = str(path)
        self._block = int(self.sample_rate * block_ms / 1000)
        self._closed = False

    def frames(self) -> Iterable[bytes]:
        from faster_whisper.audio import decode_audio

        audio = decode_audio(self._path, sampling_rate=self.sample_rate)
        pcm = (np.asarray(audio, dtype=np.float32) * 32768.0)
        pcm = pcm.clip(-32768, 32767).astype(np.int16)
        for start in range(0, pcm.shape[0], self._block):
            if self._closed:
                return
            yield pcm[start : start + self._block].tobytes()

    def close(self) -> None:
        self._closed = True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_audio_file.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/harp/audio.py tests/test_audio_file.py
git commit -m "feat(audio): FileSource — stream any ffmpeg-readable file as PCM frames

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: `HarpSession` emits `TranscriptEvent` and drives the new engine

**Files:**
- Modify: `src/harp/session.py`
- Test: `tests/test_session_stream.py`

**Interfaces:**
- Consumes: `StreamingTranscriber`, `TranscriptState`, `TranscriptEvent`,
  `SpeechDetector`, `AudioSource`.
- Produces: `HarpSession(audio, transcribe, detector, slide_interval=1.0,
  warmup=10.0, silence_threshold=0.5, max_segment=25.0, language=None)` with
  `events() -> Iterator[TranscriptEvent]`, `final_text: str`, `stop()`,
  context-manager support.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_session_stream.py
import numpy as np

from harp.audio import AudioSource
from harp.events import TranscriptEvent
from harp.session import HarpSession


class ListSource:
    sample_rate = 16000
    channels = 1

    def __init__(self, seconds):
        self._chunks = [np.zeros(int(0.5 * 16000), dtype=np.int16).tobytes()
                        for _ in range(int(seconds / 0.5))]
        self._closed = False

    def frames(self):
        for c in self._chunks:
            if self._closed:
                return
            yield c

    def close(self):
        self._closed = True


class FakeTranscribe:
    def __call__(self, audio, prompt, language):
        return "word " * max(1, audio.shape[0] // 16000)


class NoSpeech:
    def speech_segments(self, audio):
        return []


def test_session_yields_transcript_events_and_final_text():
    src = ListSource(seconds=3)
    with HarpSession(
        audio=src, transcribe=FakeTranscribe(), detector=NoSpeech(),
        slide_interval=0.0, warmup=10.0,
    ) as session:
        events = list(session.events())
    assert all(isinstance(e, TranscriptEvent) for e in events)
    assert session.final_text != ""
    assert events[-1].is_final is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_session_stream.py -v`
Expected: FAIL — `HarpSession` has no `detector` param / yields old events.

- [ ] **Step 3: Update `session.py`**

Replace the `CommitEvent` import and emission with `TranscriptEvent`, add the
`detector` parameter, pass the new engine knobs, and emit committed+transient.
Key changes (keep the existing thread/queue model):

```python
# src/harp/session.py  — imports
from harp.events import TranscriptEvent
from harp.streaming import StreamingTranscriber, TranscribeFn

# __init__ signature gains `detector` and engine knobs:
def __init__(self, audio, transcribe, detector, slide_interval=1.0,
             warmup=10.0, silence_threshold=0.5, max_segment=25.0,
             language=None):
    ...
    self._transcriber = StreamingTranscriber(
        transcribe=transcribe, detector=detector,
        samplerate=audio.sample_rate, warmup=warmup,
        silence_threshold=silence_threshold, max_segment=max_segment,
        language=language,
    )
    ...

# _run loop: emit on every step (committed and/or transient change)
def _emit(self, state) -> None:
    ev = TranscriptEvent(
        committed=state.committed.strip(),
        transient=state.transient.strip(),
        is_final=False,
        ts=time.monotonic() - self._t0,
    )
    self._queue.put(ev)

# in the worker, replace _step_and_emit/_emit usage with a state-based emit
# that fires when (committed, transient) changed since the last event.

# finalize path:
final = self._transcriber.finalize()
self._final_text = final.committed.strip()
self._queue.put(TranscriptEvent(
    committed=self._final_text, transient="", is_final=True,
    ts=time.monotonic() - self._t0,
))
self._queue.put(_SENTINEL)
```

Implement `_run` so it: pulls frames, `feed`s them, and every `slide_interval`
calls `step()` and emits a `TranscriptEvent` when `(committed, transient)`
differs from the last emitted pair. With `slide_interval=0.0` it steps on every
frame (used by the test). Always emit a terminal `is_final=True` event then the
sentinel.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_session_stream.py -v`
Expected: PASS

- [ ] **Step 5: Run the full suite + lint**

Run: `uv run pytest -q` (expect green; mark any Silero tests `slow` if slow)
Run: `uv run ruff check src tests` (expect no errors — fix as its own step, do
not pipe to `tail`)

- [ ] **Step 6: Commit**

```bash
git add src/harp/session.py tests/test_session_stream.py
git commit -m "feat(session): drive VAD engine, emit TranscriptEvent stream

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 8: `harp transcribe <file>` CLI + dark/dim display

**Files:**
- Modify: `src/harp/cli/main.py` (new `transcribe` command)
- Modify: `src/harp/cli/display.py` (render committed dark / transient dim;
  consume `TranscriptEvent`)
- Test: `tests/test_display_stream.py`

**Interfaces:**
- Consumes: `TranscriptEvent`, `FileSource`, `HarpSession`, `SileroDetector`,
  `LocalWhisperEngine`.
- Produces: CLI verb `harp transcribe PATH [--language] [--model] ...` that
  prints the streaming transcript and the final text.

- [ ] **Step 1: Write the failing test (display rendering)**

```python
# tests/test_display_stream.py
from harp.cli.display import render_line
from harp.events import TranscriptEvent


def test_render_line_marks_committed_and_transient():
    ev = TranscriptEvent(committed="hello world", transient="how are", is_final=False, ts=1.0)
    out = render_line(ev)              # returns a Rich markup string
    assert "hello world" in out
    assert "how are" in out
    assert "[dim]" in out               # transient rendered dim


def test_render_line_final_has_no_transient_markup():
    ev = TranscriptEvent(committed="hello world", transient="", is_final=True, ts=2.0)
    out = render_line(ev)
    assert out.strip().endswith("hello world") or "hello world" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_display_stream.py -v`
Expected: FAIL — `render_line` doesn't exist.

- [ ] **Step 3: Add `render_line` to `display.py`**

```python
# src/harp/cli/display.py  — add
from harp.events import TranscriptEvent


def render_line(event: TranscriptEvent) -> str:
    """Committed text in normal weight, transient in dim — Rich markup."""
    committed = event.committed
    if event.transient:
        return f"{committed} [dim]{event.transient}[/dim]".strip()
    return committed
```

(Keep the existing `TerminalDisplay`; update its `CommitEvent` import to
`TranscriptEvent` and use `event.text` where it currently reads `event.text`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_display_stream.py -v`
Expected: PASS

- [ ] **Step 5: Add the `transcribe` CLI command**

```python
# src/harp/cli/main.py  — new command
@app.command()
def transcribe(
    file: str = typer.Argument(..., help="Audio file to transcribe (wav/m4a/mp3/...)"),
    language: Optional[str] = typer.Option(None, "--language", "-l"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Whisper model size"),
) -> None:
    """Stream-transcribe an audio file, printing finalized + transient text."""
    from rich.live import Live

    from harp.audio import FileSource
    from harp.cli.display import render_line
    from harp.session import HarpSession
    from harp.vad import SileroDetector
    from harp.whisper import LocalWhisperEngine

    config = load_config(overrides={"local_language": language, "local_model": model})
    engine = LocalWhisperEngine(
        model_size=config.local_model,
        device=config.local_device,
        compute_type=config.local_compute_type,
    )
    src = FileSource(file)
    with HarpSession(
        audio=src,
        transcribe=engine.transcribe,
        detector=SileroDetector(threshold=config.stream_silence_threshold)
        if config.stream_vad else _NullDetector(),
        slide_interval=config.stream_slide_interval,
        warmup=config.stream_warmup,
        silence_threshold=config.stream_silence_threshold,
        max_segment=config.stream_max_segment,
        language=config.local_language,
    ) as session:
        with Live(console=console, refresh_per_second=8) as live:
            for ev in session.events():
                live.update(render_line(ev))
    console.print()
    console.print(session.final_text)
```

Add a tiny `_NullDetector` (returns `[]`) near the top of `main.py` for the
`stream_vad=False` path. NOTE: this command path also requires the Task 9
config fields — Task 9 lands first in the commit order below if not already
present; if running strictly in order, move Task 9 before this step or add the
fields now.

- [ ] **Step 6: Manual smoke test**

Create a short spoken WAV (or reuse a fixture) and run:
Run: `uv run harp transcribe tests/fixtures/short.wav -m base`
Expected: streaming line updates, then a final transcript prints. (Requires the
`base` model downloaded: `uv run harp models download base`.)

- [ ] **Step 7: Commit**

```bash
git add src/harp/cli/main.py src/harp/cli/display.py tests/test_display_stream.py
git commit -m "feat(cli): harp transcribe <file> with dark/dim streaming display

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 9: Config fields for the streaming engine

**Files:**
- Modify: `src/harp/config.py`
- Test: `tests/test_config.py` (add cases; create if absent)

**Interfaces:**
- Produces: `HarpConfig` gains `stream_warmup: float = 10.0`,
  `stream_silence_threshold: float = 0.5`, `stream_max_segment: float = 25.0`,
  `stream_vad: bool = True`. Removes `stream_window` and `stream_overlap`.

> Order note: if executing strictly top-to-bottom, run this task **before**
> Task 8's CLI step, since `transcribe` reads these fields. It is listed last
> only because it is the smallest/leaf change.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
from harp.config import HarpConfig


def test_streaming_defaults():
    c = HarpConfig()
    assert c.stream_warmup == 10.0
    assert c.stream_silence_threshold == 0.5
    assert c.stream_max_segment == 25.0
    assert c.stream_vad is True


def test_old_window_fields_removed():
    c = HarpConfig()
    assert not hasattr(c, "stream_window")
    assert not hasattr(c, "stream_overlap")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — new fields absent / old fields still present.

- [ ] **Step 3: Edit `config.py`**

Remove the `stream_window` and `stream_overlap` `Field`s. Add:

```python
    # STT Behavior (VAD-segmented streaming)
    stream_warmup: float = Field(
        default=10.0, description="Seconds buffered before entering chunked mode"
    )
    stream_silence_threshold: float = Field(
        default=0.5, description="Trailing silence (s) that finalizes a chunk"
    )
    stream_max_segment: float = Field(
        default=25.0, description="Force-cut length (s) when no pause is found"
    )
    stream_vad: bool = Field(
        default=True, description="Use Silero VAD for chunk boundaries"
    )
```

Then grep for any remaining `stream_window` / `stream_overlap` references and
remove them (e.g. in `cli/main.py run_daemon`, the old `start` wiring).

Run: `uv run python -c "import subprocess,sys; sys.exit(0)"` then
`grep -rn "stream_window\|stream_overlap" src` → expect no hits.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Full suite + lint + commit**

Run: `uv run pytest -q`
Run: `uv run ruff check src tests`

```bash
git add src/harp/config.py tests/test_config.py src/harp/cli/main.py
git commit -m "feat(config)!: replace stream_window/overlap with VAD engine knobs

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Notes carried to later slices (not in Slice 1)

- **Slice 2:** rewire `harp start` hotkey daemon (`run_daemon`, `on_start`) to
  build a `SileroDetector` and the new `HarpSession` signature; keep the
  clipboard sink for short dictation. The `run_daemon` wiring still references
  the old session signature and must be updated there.
- **Slice 3:** `-o transcript.md` file sink; refresh `docs/design.md`, README,
  `docs/library.md` (currently documents `CommitEvent`); CHANGELOG; add
  `AGENTS.md` + `know-how/streaming-engine.md`.

## Self-review

- **Spec coverage:** event contract (Task 1), engine warm-up/finalize/drop
  (Tasks 3–5), VAD wrapper + fallback (Task 2; `stream_vad=False` + `_NullDetector`
  in Task 8/9), FileSource (Task 6), session+CLI (Tasks 7–8), config (Task 9).
  Mic rewire, file-output sink, docs, AGENTS.md → explicitly deferred to Slices
  2–3 per the spec's slicing section. ✔
- **Placeholder scan:** all code steps carry concrete code; no TBD/TODO. ✔
- **Type consistency:** `StreamingTranscriber(transcribe, detector, …)`,
  `TranscriptState(committed, transient)`, `TranscriptEvent(committed,
  transient, is_final, ts)`, `SpeechDetector.speech_segments -> list[tuple[int,int]]`,
  `FileSource` `AudioSource` shape — consistent across Tasks 1–9. ✔
- **Known ordering hazard:** Task 9 (config) is a dependency of Task 8 (CLF);
  flagged inline in both — execute Task 9 before Task 8's CLI step.
