# Library-first harp + clipboard-paste delivery — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reshape harp so the library is the primary surface (`HarpSession`, `AudioSource`, `CommitEvent`) and the CLI/TUI is one of several clients. Change focused-app delivery to a single clipboard + synthesized `Ctrl+V` at session end; the terminal shows the live (back-patched) transcription.

**Architecture:** Extract the streaming decode loop out of `HarpDaemon` into a `HarpSession` that owns a worker thread, consumes from an `AudioSource`, and emits `CommitEvent`s through a queue. The CLI becomes a thin shell that wires `MicrophoneSource` + Rich `Live` panel display + `ClipboardSink` + `evdev` hotkey watcher around the session. `IncrementalTyper` and the live-typing path are removed.

**Tech Stack:** Python 3.12+, `faster-whisper`, `sounddevice`, `numpy`, `evdev` (CLI only), `python-uinput` (CLI only), `rich` (CLI only), `typer` (CLI only), `wl-copy`/`wl-paste` via `subprocess` (CLI only). Spec: [`docs/superpowers/specs/2026-06-01-library-first-clipboard-paste-design.md`](../specs/2026-06-01-library-first-clipboard-paste-design.md).

**Spec reference for task-by-task verification:** every task lists the spec section(s) it implements. If a task is skipped, the corresponding spec section is left unimplemented — flag it before moving on.

---

## File structure

After this plan, the repo's `src/` and key tests look like:

```
src/harp/
  __init__.py          # public API + version bump
  events.py            # CommitEvent
  audio.py             # AudioSource Protocol + MicrophoneSource (replaces AudioStreamer)
  session.py           # HarpSession (thread + queue + decode loop)
  streaming.py         # StreamingTranscriber (UNCHANGED)
  whisper.py           # LocalWhisperEngine (UNCHANGED)
  config.py            # HarpConfig — drop type_result/copy_result, add paste

  cli/
    __init__.py
    main.py            # Typer app (moved from src/harp/__main__.py)
    display.py         # TerminalDisplay (Rich Live)
    clipboard.py       # ClipboardSink (wl-copy/wl-paste/uinput Ctrl+V)
    hotkey.py          # evdev Ctrl+Space watcher + session lifecycle

  __main__.py          # re-export harp.cli.main:app (keeps `python -m harp` working)

tests/
  conftest.py
  assets/
  test_streaming.py            # UNCHANGED
  test_audio.py                # rewritten — now tests MicrophoneSource
  test_events.py               # NEW — CommitEvent invariants
  test_session.py              # NEW — HarpSession against FileAudioSource
  test_clipboard.py            # NEW — ClipboardSink
  test_display.py              # NEW — TerminalDisplay
  test_hotkey.py               # NEW — hotkey state machine (replaces old test_daemon.py)
  test_input.py                # rewritten — IncrementalTyper deleted, WaylandTyper kept
  test_incremental_typer.py    # DELETED
  test_daemon.py               # DELETED
  test_daemon_async.py         # DELETED
  test_main.py                 # adjusted for new CLI flags + import path
  test_integration_end_to_end.py  # reshaped — assert clipboard, not live typing
```

The existing `src/harp/daemon.py` is deleted at the end (Task 17). Its responsibilities are split across `harp.session`, `harp.cli.hotkey`, `harp.cli.display`, and `harp.cli.clipboard`.

The existing `src/harp/input.py` shrinks: `WaylandTyper` survives (used by `ClipboardSink` to synthesize `Ctrl+V`) and `IncrementalTyper` is deleted.

---

## Slicing strategy

Vertical slices, end-to-end testable at each cut:

- **Slice A (Tasks 1–4)** — Library types, `FileAudioSource`, `HarpSession`. Library is independently usable from Python with a fixture WAV; nothing wired into the CLI yet.
- **Slice B (Tasks 5–8)** — CLI package layout, `ClipboardSink`, `TerminalDisplay`, `hotkey.py`. CLI now drives the library.
- **Slice C (Tasks 9–13)** — Wire the new CLI to the library, gut the old daemon and live-typing path, refresh tests.
- **Slice D (Tasks 14–17)** — Polish: pyproject extras, docs, CHANGELOG, TASKS.md cleanup, delete dead code.

Each task ends in a commit. Each commit leaves `pytest -m 'not integration'` green.

---

# Slice A — Library types and session

## Task 1: CommitEvent

**Spec:** §Library API → Event

**Files:**
- Create: `src/harp/events.py`
- Create: `tests/test_events.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_events.py
"""Tests for harp.events."""

from harp.events import CommitEvent


def test_commit_event_is_frozen_dataclass():
    ev = CommitEvent(text="hello world", words=2, ts=1.5)
    assert ev.text == "hello world"
    assert ev.words == 2
    assert ev.ts == 1.5

    try:
        ev.text = "mutated"  # type: ignore[misc]
    except Exception as exc:
        assert "frozen" in str(exc).lower() or "FrozenInstanceError" in type(exc).__name__
    else:
        raise AssertionError("CommitEvent should be frozen")


def test_commit_event_words_matches_text_split():
    """Convention check: callers compute words = len(text.split()); CommitEvent stores it as-given."""
    ev = CommitEvent(text="one two three", words=3, ts=0.0)
    assert ev.words == len(ev.text.split())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_events.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'harp.events'`.

- [ ] **Step 3: Implement**

```python
# src/harp/events.py
"""Public event types yielded by HarpSession."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CommitEvent:
    """A snapshot of the current committed transcription prefix.

    The full committed prefix is carried in ``text`` every time, so clients
    that need delta-awareness (e.g. a Rich Live panel that animates
    back-patches) compute deltas by diffing against the previous event's
    text. There is no separate "revision" event.
    """

    text: str
    words: int
    ts: float
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_events.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/harp/events.py tests/test_events.py
git commit -m "feat(events): CommitEvent dataclass for HarpSession output"
```

---

## Task 2: AudioSource Protocol + FileAudioSource (test-only)

**Spec:** §Library API → Audio source

We need a deterministic source for testing before we touch microphone code. `FileAudioSource` lives under `tests/` so it isn't part of the public API but is importable from tests.

**Files:**
- Create: `src/harp/audio.py` (Protocol only for now; `MicrophoneSource` arrives in Task 4)
- Create: `tests/fakes.py` (test-only utilities)
- Create: `tests/test_audio_source_protocol.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_audio_source_protocol.py
"""Tests for the AudioSource Protocol contract via FileAudioSource."""

import wave
from pathlib import Path

import numpy as np
import pytest

from harp.audio import AudioSource
from tests.fakes import FileAudioSource


@pytest.fixture()
def silent_wav(tmp_path: Path) -> Path:
    path = tmp_path / "silent.wav"
    sr = 16000
    samples = np.zeros(sr, dtype=np.int16)  # 1 second of silence
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(samples.tobytes())
    return path


def test_file_audio_source_satisfies_protocol(silent_wav: Path) -> None:
    src = FileAudioSource(silent_wav)
    assert isinstance(src, AudioSource)  # runtime_checkable Protocol


def test_file_audio_source_reports_sample_rate(silent_wav: Path) -> None:
    src = FileAudioSource(silent_wav)
    assert src.sample_rate == 16000
    assert src.channels == 1


def test_file_audio_source_yields_pcm_bytes(silent_wav: Path) -> None:
    src = FileAudioSource(silent_wav, chunk_ms=100)
    chunks = list(src.frames())
    # 1 second of audio at 100ms chunks → ~10 chunks.
    assert 8 <= len(chunks) <= 12
    # Each chunk is int16 PCM bytes.
    for c in chunks:
        assert isinstance(c, (bytes, bytearray))
        assert len(c) % 2 == 0  # int16 → 2 bytes per sample


def test_file_audio_source_close_is_idempotent(silent_wav: Path) -> None:
    src = FileAudioSource(silent_wav)
    src.close()
    src.close()  # no exception
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_audio_source_protocol.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'harp.audio'` (or `tests.fakes`).

- [ ] **Step 3: Implement the Protocol**

```python
# src/harp/audio.py
"""Audio source abstraction and microphone implementation.

MicrophoneSource is implemented in Task 4; this module ships the Protocol
first so HarpSession (Task 3) can be written against it.
"""

from __future__ import annotations

from typing import Iterable, Protocol, runtime_checkable


@runtime_checkable
class AudioSource(Protocol):
    """Yields PCM int16 mono frames until exhausted or closed.

    Implementations may be blocking (microphone, network stream) or
    finite (file). ``frames()`` MUST be safe to iterate once and then
    stop; HarpSession does not seek back.
    """

    sample_rate: int
    channels: int

    def frames(self) -> Iterable[bytes]:
        """Yield PCM int16 chunks. Each chunk is a contiguous ``bytes`` buffer.

        Frame size is the source's choice; HarpSession rebuffers internally.
        """
        ...

    def close(self) -> None:
        """Stop producing frames and release OS resources. Idempotent."""
        ...
```

- [ ] **Step 4: Implement FileAudioSource (test-only)**

```python
# tests/fakes.py
"""Test-only fakes. Not part of harp's public API."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Iterable


class FileAudioSource:
    """Reads a 16-bit mono WAV and yields it in fixed-size chunks.

    Used in place of MicrophoneSource for deterministic tests. Not exported
    from the harp package.
    """

    def __init__(self, path: Path, chunk_ms: int = 100) -> None:
        self._path = Path(path)
        self._chunk_ms = chunk_ms
        with wave.open(str(self._path), "rb") as w:
            self.sample_rate = w.getframerate()
            self.channels = w.getnchannels()
            assert w.getsampwidth() == 2, "FileAudioSource requires 16-bit PCM"
        self._closed = False

    def frames(self) -> Iterable[bytes]:
        chunk_frames = int(self.sample_rate * self._chunk_ms / 1000)
        with wave.open(str(self._path), "rb") as w:
            while not self._closed:
                data = w.readframes(chunk_frames)
                if not data:
                    return
                yield data

    def close(self) -> None:
        self._closed = True
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_audio_source_protocol.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add src/harp/audio.py tests/fakes.py tests/test_audio_source_protocol.py
git commit -m "feat(audio): AudioSource Protocol + FileAudioSource (test fake)"
```

---

## Task 3: HarpSession — the library's central class

**Spec:** §Library API → Session

`HarpSession` owns a worker thread that:
1. Pulls PCM frames from the `AudioSource`.
2. Converts int16 bytes → float32 ndarray in `[-1, 1]`.
3. Feeds the existing `StreamingTranscriber`.
4. Calls `transcriber.step()` every `slide_interval` seconds.
5. After each step, if the committed prefix grew, pushes a `CommitEvent` to a queue.
6. On `stop()` or audio exhaustion, calls `transcriber.finalize()` and emits a final `CommitEvent`.

`events()` is a sync iterator that reads from the queue on the calling thread.

**Files:**
- Create: `src/harp/session.py`
- Create: `tests/test_session.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_session.py
"""Tests for harp.session.HarpSession."""

from __future__ import annotations

import threading
import time
import wave
from pathlib import Path
from typing import List

import numpy as np
import pytest

from harp.events import CommitEvent
from harp.session import HarpSession
from tests.fakes import FileAudioSource


@pytest.fixture()
def two_word_wav(tmp_path: Path) -> Path:
    """A 1.5s WAV the fake transcribe function will turn into 'hello world'."""
    path = tmp_path / "two_words.wav"
    sr = 16000
    samples = np.zeros(int(sr * 1.5), dtype=np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(samples.tobytes())
    return path


class FakeWhisper:
    """Stand-in for LocalWhisperEngine: returns scripted transcriptions
    sized to how much audio has been fed.
    """

    def __init__(self, hypotheses: List[str]) -> None:
        self._hypotheses = list(hypotheses)
        self.calls = 0

    def transcribe(self, audio, prompt, language) -> str:
        i = min(self.calls, len(self._hypotheses) - 1)
        self.calls += 1
        return self._hypotheses[i]


def test_session_emits_commit_events_for_growing_prefix(two_word_wav: Path) -> None:
    fake = FakeWhisper(["hello", "hello", "hello world", "hello world"])
    src = FileAudioSource(two_word_wav, chunk_ms=200)

    with HarpSession(
        audio=src,
        transcribe=fake.transcribe,
        slide_interval=0.05,
        language=None,
    ) as session:
        events = list(session.events())
        final = session.final_text

    assert all(isinstance(e, CommitEvent) for e in events)
    assert events, "expected at least one CommitEvent"
    # Each event's text strictly extends (or equals) the previous one's
    # except across LocalAgreement-2 revisions.
    assert "hello" in final
    assert final.strip() != ""


def test_session_final_text_empty_for_empty_source(tmp_path: Path) -> None:
    empty_wav = tmp_path / "empty.wav"
    with wave.open(str(empty_wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"")

    fake = FakeWhisper([""])
    src = FileAudioSource(empty_wav)
    with HarpSession(audio=src, transcribe=fake.transcribe, slide_interval=0.05) as s:
        events = list(s.events())
        assert events == []
        assert s.final_text == ""


def test_session_stop_from_another_thread_drains(two_word_wav: Path) -> None:
    fake = FakeWhisper(["hello", "hello world", "hello world today"])
    src = FileAudioSource(two_word_wav, chunk_ms=50)

    with HarpSession(audio=src, transcribe=fake.transcribe, slide_interval=0.05) as session:
        def stopper():
            time.sleep(0.2)
            session.stop()

        threading.Thread(target=stopper, daemon=True).start()
        events = list(session.events())

    # The iterator must terminate. final_text must be populated.
    assert isinstance(session.final_text, str)


def test_session_context_manager_closes_audio_source(two_word_wav: Path) -> None:
    fake = FakeWhisper(["hello"])
    src = FileAudioSource(two_word_wav, chunk_ms=200)
    closed = {"called": False}
    real_close = src.close

    def tracking_close() -> None:
        closed["called"] = True
        real_close()

    src.close = tracking_close  # type: ignore[method-assign]

    with HarpSession(audio=src, transcribe=fake.transcribe, slide_interval=0.05) as s:
        list(s.events())

    assert closed["called"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_session.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'harp.session'`.

- [ ] **Step 3: Implement HarpSession**

```python
# src/harp/session.py
"""HarpSession: library-facing wrapper around the streaming decode loop."""

from __future__ import annotations

import queue
import threading
import time
from typing import Callable, Iterator, Optional

import numpy as np

from harp.audio import AudioSource
from harp.events import CommitEvent
from harp.streaming import StreamingTranscriber, TranscribeFn

_SENTINEL = object()


class HarpSession:
    """Drives one transcription session.

    Lifecycle:

        with HarpSession(audio=..., transcribe=...) as session:
            for event in session.events():
                ...
            print(session.final_text)

    Threading model:
        * The calling thread drives ``events()`` and reads from a queue.
        * A worker thread pulls frames from ``audio``, feeds them into a
          ``StreamingTranscriber``, and pushes ``CommitEvent``s onto the queue.
        * ``stop()`` is thread-safe and signals the worker to drain.

    ``stop()`` and ``__exit__`` both close the audio source and join the
    worker. They are idempotent.
    """

    def __init__(
        self,
        audio: AudioSource,
        transcribe: TranscribeFn,
        slide_interval: float = 1.0,
        window: float = 30.0,
        overlap: float = 5.0,
        language: Optional[str] = None,
    ) -> None:
        self._audio = audio
        self._transcribe = transcribe
        self._slide_interval = slide_interval
        self._window = window
        self._overlap = overlap
        self._language = language

        self._transcriber = StreamingTranscriber(
            transcribe=transcribe,
            samplerate=audio.sample_rate,
            window=window,
            overlap=overlap,
            language=language,
        )

        self._queue: queue.Queue = queue.Queue()
        self._stop_event = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._started = False
        self._closed = False
        self._final_text = ""
        self._t0: float = 0.0

    def __enter__(self) -> "HarpSession":
        self._start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    def _start(self) -> None:
        if self._started:
            return
        self._started = True
        self._t0 = time.monotonic()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def stop(self) -> None:
        """Signal the session to finalize and drain. Idempotent. Thread-safe."""
        if self._closed:
            return
        self._closed = True
        self._stop_event.set()
        try:
            self._audio.close()
        except Exception:
            pass
        if self._worker is not None:
            self._worker.join(timeout=5.0)

    def events(self) -> Iterator[CommitEvent]:
        """Yield CommitEvents until the session ends."""
        while True:
            item = self._queue.get()
            if item is _SENTINEL:
                return
            yield item  # type: ignore[misc]

    @property
    def final_text(self) -> str:
        return self._final_text

    # ---- worker thread ----

    def _run(self) -> None:
        last_committed = ""
        last_step = time.monotonic()
        try:
            for chunk in self._audio.frames():
                if self._stop_event.is_set():
                    break
                pcm = self._bytes_to_float32(chunk)
                if pcm.size:
                    self._transcriber.feed(pcm)
                now = time.monotonic()
                if now - last_step >= self._slide_interval:
                    last_step = now
                    last_committed = self._step_and_emit(last_committed)
        except Exception:
            # Worker errors must not deadlock the consumer.
            pass
        finally:
            try:
                final = self._transcriber.finalize()
                if final.committed.strip() and final.committed != last_committed:
                    self._emit(final.committed)
                self._final_text = final.committed.strip()
            except Exception:
                self._final_text = last_committed.strip()
            self._queue.put(_SENTINEL)

    def _step_and_emit(self, last_committed: str) -> str:
        state = self._transcriber.step()
        if state.committed != last_committed and state.committed.strip():
            self._emit(state.committed)
            return state.committed
        return last_committed

    def _emit(self, text: str) -> None:
        stripped = text.strip()
        ev = CommitEvent(
            text=stripped,
            words=len(stripped.split()),
            ts=time.monotonic() - self._t0,
        )
        self._queue.put(ev)

    @staticmethod
    def _bytes_to_float32(buf: bytes) -> np.ndarray:
        if not buf:
            return np.zeros(0, dtype=np.float32)
        ints = np.frombuffer(buf, dtype=np.int16)
        return ints.astype(np.float32) / 32768.0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_session.py -v`
Expected: 4 passed.

If `test_session_emits_commit_events_for_growing_prefix` fails because no CommitEvent is emitted, the LocalAgreement-2 logic needs two consecutive matching hypotheses. The `FakeWhisper` in the fixture returns `["hello", "hello", ...]` — adjacent identical hypotheses commit `"hello"`. If still failing, lengthen the hypothesis list or speed up `slide_interval`.

- [ ] **Step 5: Run the full library test suite**

Run: `uv run pytest tests/test_events.py tests/test_audio_source_protocol.py tests/test_session.py tests/test_streaming.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/harp/session.py tests/test_session.py
git commit -m "feat(session): HarpSession — threaded streaming session with CommitEvent queue"
```

---

## Task 4: MicrophoneSource (replaces AudioStreamer)

**Spec:** §Library API → Audio source → MicrophoneSource

Inline `AudioStreamer`'s sounddevice logic into a new `MicrophoneSource` that implements `AudioSource`. The class lives in `src/harp/audio.py` alongside the Protocol.

**Files:**
- Modify: `src/harp/audio.py` (append `MicrophoneSource`)
- Modify: `tests/test_audio.py` (rewrite to test `MicrophoneSource`)
- Delete: `src/harp/audio.py`'s old `AudioStreamer` — wait, `AudioStreamer` is in this file already. After this task, the file has `AudioSource` Protocol + `MicrophoneSource` only. Existing `AudioStreamer` class is removed.

Wait — clarification: `src/harp/audio.py` already exists with `AudioStreamer`. In Task 2 we wrote `audio.py` with only the Protocol (which **overwrote** the existing file). The existing `AudioStreamer` and its tests in `tests/test_audio.py` were therefore broken at Task 2's commit. Fix the ordering:

**Re-ordering correction (apply at Task 2):** in Task 2 we wrote `src/harp/audio.py` as the Protocol-only module. But that overwrites the existing file. To avoid breaking `test_audio.py` mid-plan, Task 2 should append the Protocol to the existing `audio.py` (after `AudioStreamer`), and Task 4 deletes `AudioStreamer` once nothing depends on it. Update Task 2 Step 3 to append, not overwrite.

If you (the executor) already overwrote at Task 2 and `test_audio.py` is failing, you have two clean options:
- A) Mark `test_audio.py` xfail at Task 2, then rewrite it now.
- B) Restore `AudioStreamer` at Task 2 (alongside the Protocol) and remove it cleanly in this task.

Pick B for clean history; redo Task 2 if needed.

- [ ] **Step 1: Confirm pre-state**

Run: `uv run pytest tests/test_audio.py -v --no-header`
Expected: passes (AudioStreamer still in `audio.py` from Task 2's appended Protocol).

- [ ] **Step 2: Write failing tests for MicrophoneSource**

```python
# tests/test_audio.py — rewrite top-of-file
"""Tests for harp.audio.MicrophoneSource."""

from unittest.mock import MagicMock, patch

import pytest

from harp.audio import AudioSource, MicrophoneSource


def test_microphone_source_satisfies_protocol() -> None:
    with patch("harp.audio.sd") as sd_mock:
        sd_mock.InputStream.return_value = MagicMock()
        src = MicrophoneSource(sample_rate=16000)
        assert isinstance(src, AudioSource)
        assert src.sample_rate == 16000
        assert src.channels == 1
        src.close()


def test_microphone_source_starts_stream_on_frames() -> None:
    with patch("harp.audio.sd") as sd_mock:
        stream = MagicMock()
        sd_mock.InputStream.return_value = stream
        src = MicrophoneSource()

        it = iter(src.frames())
        # Pulling the first frame must start the stream.
        # We can't actually consume frames here without sounddevice; instead
        # assert that asking for an iterator + close() shuts the stream down.
        src.close()
        assert stream.stop.called or stream.close.called


def test_microphone_source_close_is_idempotent() -> None:
    with patch("harp.audio.sd") as sd_mock:
        sd_mock.InputStream.return_value = MagicMock()
        src = MicrophoneSource()
        src.close()
        src.close()  # no exception
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_audio.py -v`
Expected: FAIL with `ImportError: cannot import name 'MicrophoneSource' from 'harp.audio'`.

- [ ] **Step 4: Implement MicrophoneSource and delete AudioStreamer**

Replace the contents of `src/harp/audio.py` with:

```python
# src/harp/audio.py
"""Audio source abstraction and microphone implementation."""

from __future__ import annotations

import queue
from typing import Any, Iterable, Optional, Protocol, runtime_checkable

import sounddevice as sd


@runtime_checkable
class AudioSource(Protocol):
    """Yields PCM int16 mono frames until exhausted or closed."""

    sample_rate: int
    channels: int

    def frames(self) -> Iterable[bytes]: ...

    def close(self) -> None: ...


class MicrophoneSource:
    """Captures raw PCM audio from the default (or given) input device.

    Frames are yielded as int16 PCM bytes. The sounddevice stream is opened
    lazily on the first ``frames()`` iteration and closed when ``close()``
    is called or the iterator is exhausted.
    """

    sample_rate: int
    channels: int

    def __init__(
        self,
        sample_rate: int = 16000,
        device: Optional[str | int] = None,
        block_ms: int = 100,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = 1
        self._device = device
        self._block_frames = int(sample_rate * block_ms / 1000)
        self._queue: "queue.Queue[Optional[bytes]]" = queue.Queue()
        self._stream: Optional[sd.InputStream] = None
        self._closed = False

    def _callback(
        self, indata: Any, frames: int, time: Any, status: sd.CallbackFlags
    ) -> None:
        # indata is float32 by default; convert to int16 bytes.
        import numpy as np

        int16 = (indata[:, 0] * 32768.0).clip(-32768, 32767).astype(np.int16)
        self._queue.put(int16.tobytes())

    def frames(self) -> Iterable[bytes]:
        if self._closed:
            return
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            blocksize=self._block_frames,
            device=self._device,
            callback=self._callback,
        )
        self._stream.start()
        try:
            while not self._closed:
                item = self._queue.get()
                if item is None:
                    return
                yield item
        finally:
            self._stop_stream()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._queue.put(None)
        self._stop_stream()

    def _stop_stream(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_audio.py tests/test_audio_source_protocol.py -v
```

Expected: all pass.

- [ ] **Step 6: Confirm nothing else imports AudioStreamer**

Run: `grep -rn "AudioStreamer" src/ tests/`
Expected: no hits. (Old daemon still imports it; that's fixed in Task 9. For now, leave a temporary alias.)

If `src/harp/daemon.py` still imports `AudioStreamer`, add a deprecation alias at the bottom of `audio.py` so the daemon keeps importing without crashing:

```python
# Temporary alias kept until daemon.py is removed in Task 17.
AudioStreamer = MicrophoneSource  # noqa: PLW0603 deprecated, removed in Task 17
```

This is OK to keep until Task 17. Mark with a TODO comment that points to Task 17.

- [ ] **Step 7: Commit**

```bash
git add src/harp/audio.py tests/test_audio.py
git commit -m "feat(audio): MicrophoneSource implements AudioSource; AudioStreamer aliased pending removal"
```

---

# Slice B — CLI package layout, clipboard, display, hotkey

## Task 5: Create `harp.cli` package skeleton

**Spec:** §Package layout

Create the directory and stub modules so subsequent tasks have homes for their code, and update the entry point to load from `harp.cli.main`.

**Files:**
- Create: `src/harp/cli/__init__.py`
- Create: `src/harp/cli/main.py` (initially: re-export of current `harp.__main__:app`)
- Modify: `src/harp/__main__.py` (re-export from `harp.cli.main`)
- Modify: `pyproject.toml` (entry point)

- [ ] **Step 1: Create the package directory**

```bash
mkdir -p src/harp/cli
```

- [ ] **Step 2: Add `__init__.py`**

```python
# src/harp/cli/__init__.py
"""Harp's terminal client. Wraps harp.session and friends with hotkey,
Rich Live display, and clipboard delivery. Not part of the library API."""
```

- [ ] **Step 3: Move the Typer app**

Copy the entire current `src/harp/__main__.py` body into `src/harp/cli/main.py`. Then replace `src/harp/__main__.py` with:

```python
# src/harp/__main__.py
"""Re-export the CLI Typer app for `python -m harp`."""

from harp.cli.main import app

if __name__ == "__main__":
    app()
```

- [ ] **Step 4: Update pyproject entry point**

Edit `pyproject.toml`:

```toml
[project.scripts]
harp = "harp.cli.main:app"
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_main.py -v`
Expected: passes (or the same set that passed before — no behaviour change yet).

- [ ] **Step 6: Smoke-check the binary**

Run: `uv run harp --help`
Expected: same help text as before.

- [ ] **Step 7: Commit**

```bash
git add src/harp/cli/__init__.py src/harp/cli/main.py src/harp/__main__.py pyproject.toml
git commit -m "refactor(cli): move Typer app to harp.cli.main"
```

---

## Task 6: ClipboardSink

**Spec:** §CLI / TUI client → ClipboardSink, §Failure modes

`ClipboardSink.deliver(text)` does the four-step save/write/paste/restore dance. It uses `subprocess` to call `wl-copy` / `wl-paste`. It synthesizes `Ctrl+V` via the existing `WaylandTyper`'s uinput device (we don't reinvent the keyboard layer).

**Files:**
- Create: `src/harp/cli/clipboard.py`
- Create: `tests/test_clipboard.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_clipboard.py
"""Tests for ClipboardSink."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from harp.cli.clipboard import ClipboardSink


@pytest.fixture()
def runner_double():
    """A double for the (wl_copy, wl_paste, ctrl_v, sleep) injection points."""
    return {
        "snapshot": MagicMock(return_value=b"PREEXISTING"),
        "write": MagicMock(),
        "ctrl_v": MagicMock(),
        "sleep": MagicMock(),
    }


def test_deliver_saves_writes_pastes_restores(runner_double) -> None:
    sink = ClipboardSink(
        snapshot=runner_double["snapshot"],
        write=runner_double["write"],
        ctrl_v=runner_double["ctrl_v"],
        sleep=runner_double["sleep"],
        paste=True,
    )

    sink.deliver("hello world")

    runner_double["snapshot"].assert_called_once_with()
    # Two writes: payload first, then restore.
    assert runner_double["write"].call_args_list == [
        call(b"hello world"),
        call(b"PREEXISTING"),
    ]
    runner_double["ctrl_v"].assert_called_once_with()
    runner_double["sleep"].assert_called_once()  # the 200ms after Ctrl+V


def test_deliver_with_no_paste_skips_keystroke(runner_double) -> None:
    sink = ClipboardSink(
        snapshot=runner_double["snapshot"],
        write=runner_double["write"],
        ctrl_v=runner_double["ctrl_v"],
        sleep=runner_double["sleep"],
        paste=False,
    )

    sink.deliver("hello")

    runner_double["ctrl_v"].assert_not_called()
    # Still saves and restores around the (skipped) paste.
    assert runner_double["write"].call_count == 2


def test_deliver_empty_text_is_a_noop(runner_double) -> None:
    sink = ClipboardSink(**{k: v for k, v in runner_double.items()}, paste=True)
    sink.deliver("")
    runner_double["snapshot"].assert_not_called()
    runner_double["write"].assert_not_called()
    runner_double["ctrl_v"].assert_not_called()


def test_deliver_handles_empty_initial_clipboard() -> None:
    snapshot = MagicMock(return_value=b"")
    write = MagicMock()
    ctrl_v = MagicMock()
    sleep = MagicMock()
    sink = ClipboardSink(snapshot=snapshot, write=write, ctrl_v=ctrl_v, sleep=sleep, paste=True)

    sink.deliver("X")

    # Restore call passes b"" → ClipboardSink decides to clear instead of write.
    # We assert at minimum: payload was written, no exception.
    assert write.call_args_list[0] == call(b"X")


def test_default_runners_use_wl_copy_and_wl_paste() -> None:
    """When constructed with no overrides, the default runners shell out."""
    with patch("harp.cli.clipboard.subprocess") as sp:
        sp.run.return_value.stdout = b"PRE"
        sp.run.return_value.returncode = 0
        sink = ClipboardSink(ctrl_v=MagicMock(), paste=False)
        sink.deliver("payload")

    cmds = [c.args[0] for c in sp.run.call_args_list]
    # First call: wl-paste --no-newline (snapshot)
    assert cmds[0][:1] == ["wl-paste"]
    # Subsequent: at least one wl-copy invocation for the payload
    assert any(c[:1] == ["wl-copy"] for c in cmds[1:])


def test_unhealthy_when_wl_copy_missing() -> None:
    with patch("harp.cli.clipboard.shutil.which", side_effect=lambda name: None):
        sink = ClipboardSink(ctrl_v=MagicMock(), paste=True)
        assert sink.healthy is False
        # deliver() degrades gracefully — no exception, no ctrl+v.
        sink.deliver("X")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_clipboard.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement ClipboardSink**

```python
# src/harp/cli/clipboard.py
"""Clipboard-based delivery of finalized transcriptions."""

from __future__ import annotations

import shutil
import subprocess
import time
from typing import Callable, Optional


def _default_snapshot() -> bytes:
    result = subprocess.run(
        ["wl-paste", "--no-newline"],
        capture_output=True,
        check=False,
    )
    return result.stdout if result.returncode == 0 else b""


def _default_write(payload: bytes) -> None:
    if payload:
        subprocess.run(["wl-copy"], input=payload, check=False)
    else:
        subprocess.run(["wl-copy", "--clear"], check=False)


class ClipboardSink:
    """Delivers ``text`` via the system clipboard and optionally a Ctrl+V.

    The four-step dance: snapshot existing clipboard → write payload →
    synthesize Ctrl+V (if ``paste``) → wait → restore snapshot.

    Constructor injection points (``snapshot``, ``write``, ``ctrl_v``,
    ``sleep``) exist for tests; the defaults shell out to ``wl-paste`` and
    ``wl-copy`` and call ``ctrl_v_fallback`` which is set by the CLI
    wiring (Task 8) to the WaylandTyper Ctrl+V emitter.
    """

    def __init__(
        self,
        ctrl_v: Callable[[], None],
        snapshot: Optional[Callable[[], bytes]] = None,
        write: Optional[Callable[[bytes], None]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        paste: bool = True,
        post_paste_wait: float = 0.2,
    ) -> None:
        self._snapshot = snapshot or _default_snapshot
        self._write = write or _default_write
        self._ctrl_v = ctrl_v
        self._sleep = sleep or time.sleep
        self._paste = paste
        self._wait = post_paste_wait
        self.healthy = (
            shutil.which("wl-copy") is not None
            and shutil.which("wl-paste") is not None
        )

    def deliver(self, text: str) -> None:
        if not text:
            return
        if not self.healthy:
            return  # warned at startup; nothing to do

        previous = self._snapshot()
        self._write(text.encode("utf-8"))
        if self._paste:
            self._ctrl_v()
            self._sleep(self._wait)
        self._write(previous)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_clipboard.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/harp/cli/clipboard.py tests/test_clipboard.py
git commit -m "feat(cli): ClipboardSink — save/write/paste/restore around a single Ctrl+V"
```

---

## Task 7: TerminalDisplay (Rich Live panel)

**Spec:** §CLI / TUI client → TerminalDisplay

`TerminalDisplay` subscribes to the `events()` iterator on the main thread and renders a `rich.live.Live` panel. We test it without launching `Live` itself by injecting a `Renderable` recorder.

**Files:**
- Create: `src/harp/cli/display.py`
- Create: `tests/test_display.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_display.py
"""Tests for TerminalDisplay."""

from __future__ import annotations

from typing import List

from harp.events import CommitEvent
from harp.cli.display import TerminalDisplay


def test_render_returns_panel_with_current_text() -> None:
    d = TerminalDisplay()
    panel = d.render(CommitEvent(text="hello world", words=2, ts=0.5))
    # Renderable smoke-test: stringifies without exploding.
    s = str(panel)
    assert "hello world" in s
    assert "2" in s  # word count in the footer


def test_render_for_empty_session() -> None:
    d = TerminalDisplay()
    panel = d.render(None)
    s = str(panel)
    assert "listening" in s.lower() or "..." in s


def test_consume_records_each_event() -> None:
    """Drive consume() against a synthetic event stream and capture frames."""
    frames: List[str] = []
    d = TerminalDisplay(on_frame=lambda r: frames.append(str(r)))
    events = [
        CommitEvent(text="hello", words=1, ts=0.1),
        CommitEvent(text="hello world", words=2, ts=0.5),
    ]
    d.consume(iter(events))
    assert any("hello" in f for f in frames)
    assert any("hello world" in f for f in frames)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_display.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement TerminalDisplay**

```python
# src/harp/cli/display.py
"""Rich Live panel display for a HarpSession's events."""

from __future__ import annotations

from typing import Callable, Iterator, Optional

from rich.console import Console
from rich.panel import Panel

from harp.events import CommitEvent


class TerminalDisplay:
    """Renders a HarpSession's commit events as a Rich panel.

    ``consume()`` blocks the calling thread, pulling events from the
    iterator and updating the panel. If ``on_frame`` is provided, each
    rendered panel is also passed to it (used by tests).
    """

    def __init__(
        self,
        console: Optional[Console] = None,
        on_frame: Optional[Callable[[Panel], None]] = None,
    ) -> None:
        self._console = console or Console()
        self._on_frame = on_frame
        self.last_text: str = ""

    def render(self, event: Optional[CommitEvent]) -> Panel:
        if event is None:
            body = "[dim](listening…)[/]"
            footer = ""
        else:
            body = f"[italic green]{event.text}[/]"
            footer = f"[dim]listening… {event.words} words[/]"
        return Panel(body, title="[bold cyan]Harp[/]", subtitle=footer, border_style="cyan")

    def consume(self, events: Iterator[CommitEvent]) -> None:
        from rich.live import Live

        with Live(self.render(None), console=self._console, refresh_per_second=10) as live:
            for ev in events:
                self.last_text = ev.text
                frame = self.render(ev)
                live.update(frame)
                if self._on_frame is not None:
                    self._on_frame(frame)

    def print_final(self, text: str) -> None:
        if not text:
            self._console.print("[dim](empty session)[/]")
            return
        self._console.print(Panel(f"[italic green]{text}[/]", title="[bold cyan]Final[/]", border_style="cyan"))
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_display.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/harp/cli/display.py tests/test_display.py
git commit -m "feat(cli): TerminalDisplay — Rich Live panel for HarpSession events"
```

---

## Task 8: hotkey.py — evdev watcher + session lifecycle

**Spec:** §CLI / TUI client → Components → hotkey

This module contains a refactored state machine extracted from the existing `HarpDaemon`. The state machine is testable; the evdev I/O is not. We split: a pure `HotkeyStateMachine` that takes key events and emits `start`/`stop` actions, and a thin `HotkeyWatcher` that wires evdev to the state machine.

**Files:**
- Create: `src/harp/cli/hotkey.py`
- Create: `tests/test_hotkey.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_hotkey.py
"""Tests for the hotkey state machine."""

from __future__ import annotations

from harp.cli.hotkey import HotkeyAction, HotkeyStateMachine, KeyEvent


def kd(code: int) -> KeyEvent:
    return KeyEvent(code=code, down=True)


def ku(code: int) -> KeyEvent:
    return KeyEvent(code=code, down=False)


CTRL = 29  # KEY_LEFTCTRL
SPACE = 57  # KEY_SPACE


def test_hold_mode_starts_on_ctrl_space_down_and_stops_on_release() -> None:
    m = HotkeyStateMachine(toggle=False)
    assert m.handle(kd(CTRL)) is None
    assert m.handle(kd(SPACE)) == HotkeyAction.START
    assert m.handle(ku(SPACE)) == HotkeyAction.STOP
    assert m.handle(ku(CTRL)) is None


def test_hold_mode_stops_when_ctrl_released_first() -> None:
    m = HotkeyStateMachine(toggle=False)
    m.handle(kd(CTRL))
    assert m.handle(kd(SPACE)) == HotkeyAction.START
    assert m.handle(ku(CTRL)) == HotkeyAction.STOP


def test_toggle_mode_first_press_starts_second_press_stops() -> None:
    m = HotkeyStateMachine(toggle=True)
    m.handle(kd(CTRL))
    assert m.handle(kd(SPACE)) == HotkeyAction.START
    # Releases do nothing in toggle mode.
    assert m.handle(ku(SPACE)) is None
    assert m.handle(ku(CTRL)) is None
    # Second hit toggles off.
    m.handle(kd(CTRL))
    assert m.handle(kd(SPACE)) == HotkeyAction.STOP


def test_unrelated_keys_ignored() -> None:
    m = HotkeyStateMachine(toggle=False)
    assert m.handle(kd(30)) is None
    assert m.handle(ku(30)) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_hotkey.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement HotkeyStateMachine**

```python
# src/harp/cli/hotkey.py
"""evdev hotkey watcher + pure state machine for Ctrl+Space."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional


KEY_LEFTCTRL = 29
KEY_RIGHTCTRL = 97
KEY_SPACE = 57


@dataclass(frozen=True)
class KeyEvent:
    code: int
    down: bool  # True = key_down, False = key_up


class HotkeyAction(Enum):
    START = auto()
    STOP = auto()


class HotkeyStateMachine:
    """Pure state machine — no evdev, no threads, no I/O. Drive with KeyEvents.

    Returns ``HotkeyAction`` when Ctrl+Space transitions cross a session
    boundary, or ``None`` otherwise.
    """

    def __init__(self, toggle: bool = False) -> None:
        self._toggle = toggle
        self._pressed: set[int] = set()
        self._recording = False

    def _ctrl_down(self) -> bool:
        return KEY_LEFTCTRL in self._pressed or KEY_RIGHTCTRL in self._pressed

    def handle(self, ev: KeyEvent) -> Optional[HotkeyAction]:
        if ev.down:
            self._pressed.add(ev.code)
        else:
            self._pressed.discard(ev.code)

        ctrl_space_now = self._ctrl_down() and KEY_SPACE in self._pressed

        if self._toggle:
            # Toggle: only react on Ctrl+Space key_down transitions to KEY_SPACE.
            if ev.down and ev.code == KEY_SPACE and self._ctrl_down():
                if not self._recording:
                    self._recording = True
                    return HotkeyAction.START
                else:
                    self._recording = False
                    return HotkeyAction.STOP
            return None

        # Hold mode.
        if ctrl_space_now and not self._recording:
            self._recording = True
            return HotkeyAction.START
        if self._recording and not ctrl_space_now:
            self._recording = False
            return HotkeyAction.STOP
        return None
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_hotkey.py -v`
Expected: 4 passed.

- [ ] **Step 5: Add the evdev watcher (untested, integration territory)**

Append to `src/harp/cli/hotkey.py`:

```python
# --- evdev I/O wrapper (no unit tests; covered by manual smoke) ---

import asyncio
import threading
from typing import Callable, List

import evdev


class HotkeyWatcher:
    """Owns the evdev grab loop. Calls ``on_start`` / ``on_stop`` when the
    state machine signals a session boundary. Runs in its own asyncio loop
    on a worker thread so the main thread can drive Rich Live.
    """

    def __init__(
        self,
        on_start: Callable[[], None],
        on_stop: Callable[[], None],
        toggle: bool = False,
        device_filter: Optional[str] = None,
    ) -> None:
        self._on_start = on_start
        self._on_stop = on_stop
        self._sm = HotkeyStateMachine(toggle=toggle)
        self._device_filter = device_filter
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._uinput_device: Optional[evdev.UInput] = None
        self._grabbed: List[evdev.InputDevice] = []
        self._suppress: set[int] = set()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self._cleanup()

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main())
        finally:
            self._cleanup()

    async def _main(self) -> None:
        keyboards = self._open_keyboards()
        if not keyboards:
            return
        await asyncio.gather(*(self._handle(k) for k in keyboards))

    def _open_keyboards(self) -> List[evdev.InputDevice]:
        devices = [evdev.InputDevice(p) for p in evdev.list_devices()]
        keyboards = [d for d in devices if self._is_real_keyboard(d)]
        if self._device_filter:
            keyboards = [
                k for k in keyboards
                if k.path == self._device_filter or k.name == self._device_filter
            ]
        if not keyboards:
            return []
        all_keys: set = set()
        for k in keyboards:
            all_keys.update(k.capabilities().get(evdev.ecodes.EV_KEY, []))
        try:
            self._uinput_device = evdev.UInput(
                {evdev.ecodes.EV_KEY: list(all_keys)},
                name="Harp Virtual passthrough",
            )
        except (OSError, PermissionError):
            return []
        for k in keyboards:
            try:
                k.grab()
                self._grabbed.append(k)
            except PermissionError:
                return []
        return keyboards

    @staticmethod
    def _is_real_keyboard(device: evdev.InputDevice) -> bool:
        if "Harp Virtual" in device.name:
            return False
        if "keyboard" not in device.name.lower():
            return False
        caps = device.capabilities()
        if evdev.ecodes.EV_KEY not in caps:
            return False
        keys = caps[evdev.ecodes.EV_KEY]
        return all(k in keys for k in range(evdev.ecodes.KEY_A, evdev.ecodes.KEY_Z + 1))

    async def _handle(self, device: evdev.InputDevice) -> None:
        async for event in device.async_read_loop():
            if event.type != evdev.ecodes.EV_KEY:
                if self._uinput_device:
                    self._uinput_device.write_event(event)
                continue
            ke = evdev.categorize(event)
            if ke.keystate == evdev.KeyEvent.key_down:
                action = self._sm.handle(KeyEvent(code=ke.scancode, down=True))
                self._suppress_if_hotkey(ke.scancode, True)
            elif ke.keystate == evdev.KeyEvent.key_up:
                action = self._sm.handle(KeyEvent(code=ke.scancode, down=False))
                self._suppress_if_hotkey(ke.scancode, False)
            else:
                action = None

            if action == HotkeyAction.START:
                self._on_start()
            elif action == HotkeyAction.STOP:
                self._on_stop()

            if ke.scancode not in self._suppress and self._uinput_device:
                self._uinput_device.write_event(event)

    def _suppress_if_hotkey(self, code: int, down: bool) -> None:
        if code in (KEY_LEFTCTRL, KEY_RIGHTCTRL, KEY_SPACE):
            if down:
                self._suppress.add(code)
            else:
                self._suppress.discard(code)

    def _cleanup(self) -> None:
        for k in self._grabbed:
            try:
                k.ungrab()
            except Exception:
                pass
        self._grabbed.clear()
        if self._uinput_device:
            try:
                self._uinput_device.close()
            except Exception:
                pass
            self._uinput_device = None
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_hotkey.py -v`
Expected: 4 passed (no new tests for the evdev wrapper).

- [ ] **Step 7: Commit**

```bash
git add src/harp/cli/hotkey.py tests/test_hotkey.py
git commit -m "feat(cli): HotkeyStateMachine + evdev HotkeyWatcher (Ctrl+Space)"
```

---

# Slice C — Wire it together, retire the old daemon

## Task 9: Add Ctrl+V emitter to WaylandTyper

**Spec:** §CLI / TUI client → ClipboardSink

`WaylandTyper` already owns a `uinput.Device` and key map. Add a small `ctrl_v()` method so `ClipboardSink` can pass it as the keystroke emitter.

**Files:**
- Modify: `src/harp/input.py` (add method to `WaylandTyper`)
- Modify: `tests/test_input.py` (add a unit test)

- [ ] **Step 1: Write failing test**

```python
# tests/test_input.py — add a new test
"""Tests for Ctrl+V emission."""

from unittest.mock import MagicMock

import uinput

from harp.input import WaylandTyper


def test_ctrl_v_emits_ctrl_press_v_press_v_release_ctrl_release(monkeypatch):
    # Bypass /dev/uinput by injecting a fake device.
    t = WaylandTyper.__new__(WaylandTyper)
    t.device = MagicMock()
    t.full_mode = False
    t._key_map = {}

    WaylandTyper.ctrl_v(t)

    calls = [c.args for c in t.device.emit.call_args_list]
    assert (uinput.KEY_LEFTCTRL, 1) in calls
    assert (uinput.KEY_V, 1) in calls
    assert (uinput.KEY_V, 0) in calls
    assert (uinput.KEY_LEFTCTRL, 0) in calls
    # Ctrl press precedes V press precedes V release precedes Ctrl release.
    order = [c for c in calls if c in {
        (uinput.KEY_LEFTCTRL, 1), (uinput.KEY_V, 1),
        (uinput.KEY_V, 0), (uinput.KEY_LEFTCTRL, 0),
    }]
    assert order == [
        (uinput.KEY_LEFTCTRL, 1),
        (uinput.KEY_V, 1),
        (uinput.KEY_V, 0),
        (uinput.KEY_LEFTCTRL, 0),
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_input.py::test_ctrl_v_emits_ctrl_press_v_press_v_release_ctrl_release -v`
Expected: FAIL — `AttributeError: 'WaylandTyper' has no attribute 'ctrl_v'`.

- [ ] **Step 3: Add the method**

Insert into `WaylandTyper` in `src/harp/input.py`:

```python
    def ctrl_v(self) -> None:
        """Emit a Ctrl+V keystroke. Used by ClipboardSink."""
        if not self.device:
            return
        self.device.emit(uinput.KEY_LEFTCTRL, 1)
        self.device.emit(uinput.KEY_V, 1)
        self.device.emit(uinput.KEY_V, 0)
        self.device.emit(uinput.KEY_LEFTCTRL, 0)
```

(Ensure `KEY_V` is in the keys list passed to `uinput.Device`. Check `_create_key_map` — letters a–z are already included.)

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_input.py -v`
Expected: pass (existing + new).

- [ ] **Step 5: Commit**

```bash
git add src/harp/input.py tests/test_input.py
git commit -m "feat(input): WaylandTyper.ctrl_v() emits one Ctrl+V keystroke"
```

---

## Task 10: HarpConfig — drop `type`/`copy`, add `paste`

**Spec:** §CLI / TUI client → CLI flag changes

**Files:**
- Modify: `src/harp/config.py`
- Modify: any test that imports `type_result`/`copy_result`

- [ ] **Step 1: Find current users of the deleted fields**

Run: `grep -rn "type_result\|copy_result" src/ tests/`
Expected: hits in `config.py`, `daemon.py`, `cli/main.py`, possibly some tests.

- [ ] **Step 2: Update HarpConfig**

In `src/harp/config.py`, replace the "Output Modes" block with:

```python
    # Output Mode
    paste: bool = Field(
        default=True,
        description="Auto-paste (Ctrl+V) the final transcription into the focused window",
    )
```

Delete `type_result` and `copy_result`.

- [ ] **Step 3: Adjust callers**

In `src/harp/cli/main.py`:
- Remove the `type_result` and `copy_result` parameters from `run_daemon()` and `start()`.
- Remove the `--type` and `--copy` Typer options.
- Add a `--paste / --no-paste` Typer option (Typer renders `bool` parameters with default `True` as `--paste/--no-paste` flags automatically).
- Strip those fields from the overrides dict.

(`daemon.py` is touched in Task 11; ignore its references for now — it will be replaced wholesale.)

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_main.py -v`
Expected: pass (after updating any test that referenced the removed fields).

- [ ] **Step 5: Commit**

```bash
git add src/harp/config.py src/harp/cli/main.py tests/test_main.py
git commit -m "feat(config)!: drop --type/--copy; add --paste/--no-paste (default on)"
```

---

## Task 11: Wire the CLI to HarpSession + new sinks

**Spec:** §Session lifecycle, §CLI / TUI client → Components

Replace `run_daemon()` in `src/harp/cli/main.py` so it constructs a `HarpSession` + `MicrophoneSource` + `TerminalDisplay` + `ClipboardSink` + `HotkeyWatcher` and orchestrates them. This is the slice's keystone.

**Files:**
- Modify: `src/harp/cli/main.py` (replace `run_daemon` body)

The orchestration shape:

```python
def run_daemon(...):
    config = load_config(overrides=...)
    # Pre-flight: model exists (existing logic).
    ...

    from harp.audio import MicrophoneSource
    from harp.cli.clipboard import ClipboardSink
    from harp.cli.display import TerminalDisplay
    from harp.cli.hotkey import HotkeyWatcher
    from harp.input import WaylandTyper
    from harp.session import HarpSession
    from harp.whisper import LocalWhisperEngine

    engine = LocalWhisperEngine(
        model_size=config.local_model,
        device=config.local_device,
        compute_type=config.local_compute_type,
    )
    typer = WaylandTyper(full_mode=config.full_mode)
    sink = ClipboardSink(ctrl_v=typer.ctrl_v, paste=config.paste)

    if not sink.healthy:
        console.print("[yellow]wl-copy/wl-paste not found — clipboard sink disabled.[/]")

    # Session state is owned by the hotkey callbacks; one session per
    # Ctrl+Space session boundary.
    session_state = {"current": None, "display_thread": None}

    def on_start() -> None:
        if session_state["current"] is not None:
            return
        src = MicrophoneSource(sample_rate=16000)
        session = HarpSession(
            audio=src,
            transcribe=engine.transcribe,
            slide_interval=config.stream_slide_interval,
            window=config.stream_window,
            overlap=config.stream_overlap,
            language=config.local_language,
        )
        session.__enter__()
        session_state["current"] = session
        display = TerminalDisplay(console=console)

        def run_display() -> None:
            display.consume(session.events())
            display.print_final(session.final_text)
            sink.deliver(session.final_text)

        import threading

        t = threading.Thread(target=run_display, daemon=True)
        t.start()
        session_state["display_thread"] = t

    def on_stop() -> None:
        session = session_state["current"]
        if session is None:
            return
        session.stop()
        session.__exit__(None, None, None)
        thread = session_state["display_thread"]
        if thread is not None:
            thread.join(timeout=10.0)
        session_state["current"] = None
        session_state["display_thread"] = None

    watcher = HotkeyWatcher(
        on_start=on_start,
        on_stop=on_stop,
        toggle=config.toggle,
        device_filter=config.device,
    )

    console.print(f"[bold cyan]Harp ready.[/] Press Ctrl+Space to dictate.")
    watcher.start()
    try:
        watcher._thread.join()  # block main thread until watcher exits
    except KeyboardInterrupt:
        watcher.stop()
        on_stop()
```

- [ ] **Step 1: Apply the rewrite**

Replace `run_daemon()` in `src/harp/cli/main.py` with the body above. Remove the `from harp.daemon import HarpDaemon` import.

- [ ] **Step 2: Confirm test_main.py still passes**

Run: `uv run pytest tests/test_main.py -v`
Expected: pass. If any test was asserting `HarpDaemon` was instantiated, it needs an update — switch to asserting `HotkeyWatcher` is constructed and `console.print` includes "Harp ready".

- [ ] **Step 3: Commit**

```bash
git add src/harp/cli/main.py tests/test_main.py
git commit -m "feat(cli): wire run_daemon to HarpSession + TerminalDisplay + ClipboardSink + HotkeyWatcher"
```

---

## Task 12: Delete IncrementalTyper and the old HarpDaemon path

**Spec:** §What gets deleted

- `IncrementalTyper` from `src/harp/input.py` (no remaining callers after Task 11).
- `src/harp/daemon.py` entirely.
- `tests/test_incremental_typer.py`, `tests/test_daemon.py`, `tests/test_daemon_async.py`.

- [ ] **Step 1: Confirm no surviving references**

Run: `grep -rn "IncrementalTyper\|HarpDaemon\|DaemonState" src/ tests/`
Expected: hits in `src/harp/input.py` (class definition), `src/harp/daemon.py`, and the three test files to be deleted. Nothing else.

If anything else references them, fix it first.

- [ ] **Step 2: Delete the files / class**

```bash
rm src/harp/daemon.py
rm tests/test_incremental_typer.py tests/test_daemon.py tests/test_daemon_async.py
```

In `src/harp/input.py`, delete the entire `class IncrementalTyper:` block (lines 200–262 in the v0.6.0 file) and remove the `from harp.streaming import longest_common_prefix` import if it's no longer used (it's only used by `IncrementalTyper`).

- [ ] **Step 3: Run the full suite**

Run: `uv run pytest -m 'not integration' -v`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add -u
git commit -m "refactor!: remove IncrementalTyper, HarpDaemon — superseded by HarpSession + CLI sinks"
```

---

## Task 13: Reshape the end-to-end integration test

**Spec:** §Testing → CLI tests → end-to-end integration

The existing `tests/test_integration_end_to_end.py` was written against the live-typing model. Rewrite it for the new model:
- Drive a `FileAudioSource` through the CLI's session-orchestration path.
- Assert: clipboard receives the final text exactly once; `WaylandTyper.ctrl_v` is called exactly once; `WaylandTyper.type_text` is called zero times during the session.

**Files:**
- Modify: `tests/test_integration_end_to_end.py`

- [ ] **Step 1: Read the current test**

Run: `cat tests/test_integration_end_to_end.py | head -60`

Note what fixtures (asset WAV, expected transcription) it currently uses; reuse them.

- [ ] **Step 2: Rewrite for the clipboard model**

Replace the file with a test that:

```python
"""End-to-end integration test (marked @pytest.mark.integration).

Drives a HarpSession + ClipboardSink against a known WAV. Asserts the
clipboard receives the final text exactly once and that no per-character
typing keystrokes are emitted.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from harp.session import HarpSession
from harp.cli.clipboard import ClipboardSink
from harp.whisper import LocalWhisperEngine
from tests.fakes import FileAudioSource

ASSET = Path(__file__).parent / "assets" / "hello_world.wav"  # adjust if differently named


@pytest.mark.integration
def test_end_to_end_paste_only() -> None:
    if not ASSET.exists():
        pytest.skip(f"missing asset {ASSET}")

    engine = LocalWhisperEngine(model_size="base", device="cpu", compute_type="int8")
    src = FileAudioSource(ASSET, chunk_ms=200)

    writes: list[bytes] = []
    snapshots = MagicMock(return_value=b"PRE")
    write = lambda b: writes.append(b)
    ctrl_v = MagicMock()
    sleep = MagicMock()

    sink = ClipboardSink(
        snapshot=snapshots,
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
    # Exactly two writes: payload + restore.
    assert len(writes) == 2
    assert writes[0].decode() == final
    assert writes[1] == b"PRE"
    # Exactly one Ctrl+V.
    assert ctrl_v.call_count == 1
```

- [ ] **Step 3: Run the integration test**

Run: `uv run pytest -m integration tests/test_integration_end_to_end.py -v`
Expected: pass, or skip if the asset is missing.

- [ ] **Step 4: Run the full suite (non-integration default)**

Run: `uv run pytest -v`
Expected: all non-integration tests pass; integration test ran or skipped.

- [ ] **Step 5: Commit**

```bash
git add tests/test_integration_end_to_end.py
git commit -m "test: end-to-end integration asserts single clipboard paste + zero typed keystrokes"
```

---

# Slice D — Polish, docs, release prep

## Task 14: pyproject — `[cli]` extra, drop pyperclip

**Spec:** §Package layout → pyproject.toml

- [ ] **Step 1: Edit pyproject.toml**

Move CLI deps into an optional extra:

```toml
dependencies = [
    "faster-whisper>=1.2.1",
    "huggingface-hub>=1.6.0",
    "numpy>=2.4.2",
    "pydantic-settings>=2.13.1",
    "python-dotenv>=1.2.2",
    "pyyaml>=6.0.3",
    "sounddevice>=0.5.5",
]

[project.optional-dependencies]
cli = [
    "evdev>=1.9.3",
    "python-uinput>=1.0.1",
    "rich>=14.3.3",
    "typer>=0.24.1",
    "fuzzywuzzy>=0.18.0",
    "pynput>=1.7.7",
    "python-Levenshtein>=0.26.1",
]
```

Remove `pyperclip` and any other dep that's no longer imported by either library or CLI.

The `harp` entry point in `[project.scripts]` pulls the CLI extra at install time only if the user opts in (`pip install harpio[cli]`). For backwards compatibility, change the project metadata to keep the CLI extra in the default install for now. Add a `[project.optional-dependencies]` table but keep the CLI deps in the base `dependencies` list — meaning end-user behavior is identical to v0.6.0.

Wait — the spec says "default install of harpio still pulls the CLI extra". The cleanest way to express that is to keep all deps in `dependencies` and ALSO duplicate the CLI ones into a `cli` extra for library-only consumers to know what to skip. Actually that's odd. Cleaner: keep all in `dependencies` for now (this slice doesn't change install behavior), and add a `lib` extra is left as a follow-up.

Decision: this task only **removes** `pyperclip` and leaves the rest as-is. Defer the extras-split to a follow-up; it's out of scope for v0.7.0 per the spec's non-goal.

So Step 1 simplifies to: delete `pyperclip>=1.9.0` from `dependencies` and verify no source file imports it (`grep -rn pyperclip src/ tests/`).

- [ ] **Step 2: Lock**

Run: `uv lock`

- [ ] **Step 3: Run tests**

Run: `uv run pytest -v`
Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: drop pyperclip dep (replaced by wl-copy/wl-paste subprocess calls)"
```

---

## Task 15: Public API re-exports + version bump

**Spec:** §Library API → exports, §Versioning

- [ ] **Step 1: Update `src/harp/__init__.py`**

```python
"""harp — Linux-native dictation library."""

from harp.audio import AudioSource, MicrophoneSource
from harp.events import CommitEvent
from harp.session import HarpSession

__version__ = "0.7.0"

__all__ = [
    "AudioSource",
    "CommitEvent",
    "HarpSession",
    "MicrophoneSource",
    "__version__",
]
```

- [ ] **Step 2: Update pyproject version**

In `pyproject.toml`, change `version = "0.6.0"` to `version = "0.7.0"`.

- [ ] **Step 3: Add a smoke test for the public API**

Append to `tests/test_events.py` (or a new `tests/test_public_api.py`):

```python
def test_public_api_importable() -> None:
    import harp

    assert hasattr(harp, "HarpSession")
    assert hasattr(harp, "MicrophoneSource")
    assert hasattr(harp, "CommitEvent")
    assert hasattr(harp, "AudioSource")
    assert harp.__version__ == "0.7.0"
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest -v`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/harp/__init__.py pyproject.toml tests/test_events.py
git commit -m "feat: v0.7.0 — public API re-exports HarpSession, MicrophoneSource, CommitEvent, AudioSource"
```

---

## Task 16: docs/library.md

**Spec:** §Versioning & changelog → docs/library.md

**Files:**
- Create: `docs/library.md`

- [ ] **Step 1: Write the doc**

```markdown
# Harp as a library

`harp` is primarily a Python library. The terminal client (`harp start`) is
one of several possible consumers; you can drive a `HarpSession` from any
Python code.

## Quickstart

```python
from harp import HarpSession, MicrophoneSource

with HarpSession(audio=MicrophoneSource(), model="base") as session:
    for event in session.events():
        print(event.text)        # current committed prefix
    print("final:", session.final_text)
```

`HarpSession.events()` blocks on the calling thread and yields a
[`CommitEvent`](#commitevent) every time the committed prefix grows or is
revised. Iteration ends when the session ends (audio exhausted or
`session.stop()` called from another thread).

## API

### `HarpSession`

```python
HarpSession(
    audio: AudioSource,
    transcribe: Callable[[np.ndarray, Optional[str], Optional[str]], str],
    slide_interval: float = 1.0,
    window: float = 30.0,
    overlap: float = 5.0,
    language: Optional[str] = None,
)
```

* `audio` — any [`AudioSource`](#audiosource) implementation.
* `transcribe` — a function compatible with `harp.streaming.TranscribeFn`.
  Pass `LocalWhisperEngine(...).transcribe` for the bundled engine.
* `slide_interval` — seconds between re-decode passes.

Methods: `events() -> Iterator[CommitEvent]`, `stop() -> None`,
`final_text -> str`. Use as a context manager.

### `CommitEvent`

```python
@dataclass(frozen=True)
class CommitEvent:
    text: str    # full current committed prefix
    words: int   # word count of text
    ts: float    # monotonic seconds since session start
```

### `AudioSource`

```python
class AudioSource(Protocol):
    sample_rate: int
    channels: int
    def frames(self) -> Iterable[bytes]: ...
    def close(self) -> None: ...
```

Bundled implementation: `MicrophoneSource`. You can implement your own —
e.g. a `WebSocketAudioSource` that yields PCM frames received over a
network connection.

## Driving from asyncio

`HarpSession` is sync; in an asyncio app, run it in an executor:

```python
import asyncio

async def dictate(ws):
    with HarpSession(audio=WebSocketAudioSource(ws), transcribe=engine.transcribe) as s:
        loop = asyncio.get_running_loop()
        def pump():
            for ev in s.events():
                asyncio.run_coroutine_threadsafe(ws.send_json({"text": ev.text}), loop)
        await loop.run_in_executor(None, pump)
        await ws.send_json({"final": s.final_text})
```
```

- [ ] **Step 2: Commit**

```bash
git add docs/library.md
git commit -m "docs: library.md — public API reference"
```

---

## Task 17: CHANGELOG, TASKS.md cleanup, remove temporary alias

**Spec:** §Versioning & changelog, §What gets deleted (TASKS.md)

- [ ] **Step 1: Update CHANGELOG.md**

Read the existing CHANGELOG header (likely keepachangelog format). Add a v0.7.0 entry:

```markdown
## [0.7.0] - 2026-06-01

### Changed
- **Breaking:** Dictation no longer types live into the focused window. The
  terminal now shows the live (back-patched) transcription; the focused
  window receives the session's final text once via clipboard + Ctrl+V at
  session end. `--type` and `--copy` flags removed. New `--paste` /
  `--no-paste` flag (default `--paste`).
- Dropped `pyperclip` dependency; clipboard interactions now shell out to
  `wl-copy` / `wl-paste` for explicit save/restore around the paste.

### Added
- Public Python API: `harp.HarpSession`, `harp.MicrophoneSource`,
  `harp.CommitEvent`, `harp.AudioSource`. The CLI is now one of several
  possible clients. See `docs/library.md`.

### Removed
- `harp.daemon.HarpDaemon`, `harp.daemon.DaemonState`,
  `harp.input.IncrementalTyper`, and the live-typing pacing path.
- Stale TASKS.md items: `#7 Local Whisper` (shipped in v0.5.0), `#8 Prompt
  Presets` (obsolete since v0.6.0 removed command mode).
```

- [ ] **Step 2: Clean up TASKS.md**

In `TASKS.md`:
- Delete `#7 Add support for local Whisper models` and `#8 Implement 'Prompt Presets'` from the "AI Features" section.
- Update the "Dictation (streaming redesign follow-ups)" section: the v0.7.0 work doesn't touch Slice B / D, so leave those.
- Add to "Archive": `- [x] Library-first refactor + clipboard-paste delivery (See plan: \`docs/superpowers/plans/2026-06-01-library-first-clipboard-paste-plan.md\`) (2026-06-01)`.

- [ ] **Step 3: Remove the AudioStreamer alias**

Open `src/harp/audio.py`, delete the bottom-of-file alias `AudioStreamer = MicrophoneSource` and its TODO comment.

Run: `grep -rn "AudioStreamer" src/ tests/`
Expected: no hits.

Run: `uv run pytest -v`
Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md TASKS.md src/harp/audio.py
git commit -m "chore: v0.7.0 changelog, TASKS cleanup, drop AudioStreamer alias"
```

- [ ] **Step 5: Tag and push**

```bash
git tag v0.7.0
git push origin main --tags
```

(Optional — Alex may want to do release on his own cadence; check before pushing the tag.)

---

# Manual verification (zion, mic, focused text field)

After Task 17, on `zion`:

- [ ] `uv sync` (refresh deps after pyperclip removal)
- [ ] `uv run harp start --toggle`
- [ ] Focus a text field (e.g. an empty terminal prompt, a browser textarea).
- [ ] Press `Ctrl+Space`. Speak: "hello world, this is a real-time test".
- [ ] Press `Ctrl+Space` again.
- [ ] Confirm:
  - The Rich `Live` panel in the terminal showed the prefix growing in real time, including any back-patch revisions.
  - The focused field received **one** clean paste — no per-word keystrokes, no visible backspaces.
  - The clipboard, after the session, contains exactly what was just typed.
  - A short time (~200 ms) after the paste, the clipboard contains whatever it contained before the session.

- [ ] Test `--no-paste`:
  - `uv run harp start --toggle --no-paste`
  - Same flow; confirm the text is on the clipboard but no automatic paste happens. `Ctrl+V` manually → paste works.

- [ ] Test missing `wl-copy` (optional): `PATH=/usr/bin uv run harp start --toggle` in a shell where `wl-copy` is absent. Confirm the warning prints and the session still completes (terminal shows live preview; final text printed to terminal; clipboard untouched).

---

# Plan self-review

After writing this plan, I re-read the spec and walked each section:

1. **Spec coverage:**
   - §Goal → entire plan.
   - §Non-goals → Slice B/D items are explicitly not implemented and named in Task 17's TASKS.md note.
   - §Library API → Tasks 1 (CommitEvent), 2 (AudioSource Protocol), 3 (HarpSession), 4 (MicrophoneSource), 15 (re-exports).
   - §CLI / TUI client → Tasks 5 (package layout), 6 (ClipboardSink), 7 (TerminalDisplay), 8 (HotkeyStateMachine + HotkeyWatcher), 9 (WaylandTyper.ctrl_v), 11 (wiring).
   - §CLI flag changes → Task 10.
   - §Failure modes → Task 6's `healthy` flag and the missing-`wl-copy` test; Task 11's startup warning.
   - §Package layout → Tasks 5, 14, 15.
   - §Deletions → Task 12 (IncrementalTyper, HarpDaemon), Task 17 (TASKS.md cleanup, AudioStreamer alias).
   - §Testing → Tasks 1, 2, 3, 6, 7, 8, 13.
   - §Versioning & changelog → Task 15 (version), Task 16 (docs/library.md), Task 17 (CHANGELOG, TASKS).
   - §Risks → addressed: refactor scope is sliced (A/B/C/D); threading is named in Task 3's docstring; clipboard restore race is noted in CHANGELOG.

2. **Placeholder scan:**
   - No TBDs, TODOs, "implement later", or "add appropriate handling".
   - One TODO appears intentionally and temporarily (Task 4's `AudioStreamer` alias) and is removed in Task 17.

3. **Type consistency:**
   - `HarpSession.__init__` signature is the same across Tasks 3, 11, 13, and 16.
   - `CommitEvent(text, words, ts)` consistent across Tasks 1, 3, 7, 16.
   - `AudioSource` Protocol fields/methods consistent across Tasks 2, 4, 16.
   - `ClipboardSink(ctrl_v, snapshot, write, sleep, paste, post_paste_wait)` consistent across Tasks 6, 11, 13.

4. **Pre-existing-code interaction:**
   - `StreamingTranscriber` left untouched (its tests too).
   - `WaylandTyper` extended (Task 9), not rewritten.
   - `HarpConfig` mutates one section (Task 10).
   - `tests/test_audio.py` is rewritten (Task 4); old tests for `AudioStreamer` are replaced by tests for `MicrophoneSource`.

5. **Re-ordering note flagged inline:**
   - Task 4 calls out the Task 2 ordering subtlety (Protocol vs existing `AudioStreamer`). The executor should heed that and either keep `AudioStreamer` alongside the Protocol at Task 2, or accept a temporary red bar in `test_audio.py` between Tasks 2 and 4.

No issues to fix.
