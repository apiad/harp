# Full (dictation) mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `DictationSession` (record-then-transcribe) primitive to harp for bounded push-to-talk utterances, then rewrite aegis's voice path to consume it — eliminating the warmup/tail-drop/seam defects of driving the long-form streaming engine for short-form dictation.

**Architecture:** harp gains `src/harp/dictation.py::DictationSession` — a worker thread buffers mic frames while recording (no decoding), and `stop()` drains the buffer, decodes the whole clip once against an injected warm `transcribe`, and returns the text. aegis's `VoiceSession`/`_default_factory` are rewritten to build a `DictationSession` and insert the final text in one shot on stop; the streaming/marshalling/delta machinery is deleted.

**Tech Stack:** Python 3.12+ (harp) / 3.13 (aegis), `faster-whisper`, `numpy`, `sounddevice`, Textual 8.2.6, `uv`, pytest.

## Global Constraints

- **harp:** commit straight to `main`, conventional commits; TDD; lint as its own step `uv run ruff check src tests` (harp lints both); `make test` fast / `make test-integration` slow. The engine stays pure/fake-testable (no model load in unit tests). `import harp` must not import `sounddevice` at module load.
- **aegis:** commit straight to `main`; TDD; real lint gate is `uv run ruff check src/` (NOT `tests`); never `import harp` at module load (only inside `_get_engine`/factory/`prewarm`); voice stays feature-detected and off by default.
- **Dependency direction:** aegis depends on `harpio` (base + `sounddevice`), never `harpio[cli]`.
- **Phasing:** harp ships + releases first, then aegis bumps the pin.

---

## File Structure

**harp:**
- Modify `src/harp/audio.py` — add module-level `bytes_to_float32(buf) -> np.ndarray` (extracted, shared).
- Modify `src/harp/session.py` — use the shared `bytes_to_float32` (drop the duplicate staticmethod body).
- Create `src/harp/dictation.py` — `DictationSession`.
- Modify `src/harp/__init__.py` — export `DictationSession`.
- Tests: `tests/test_dictation.py`.
- Bump `pyproject.toml` version.

**aegis:**
- Modify `src/aegis/voice/session.py` — `_default_factory` builds `DictationSession`; rewrite `VoiceSession` (single `on_final`, off-thread decode). Keep `_get_engine`, `prewarm`.
- Modify `src/aegis/tui/app.py` — simplify voice wiring (drop `_on_voice_update`; per-session pane/base capture; single insert on stop).
- Modify `pyproject.toml` — bump `harpio` pin.
- Tests: `tests/test_voice_factory.py`, `tests/test_voice_action.py`.

---

# PHASE A — harp: `DictationSession`

## Task A1: Shared `bytes_to_float32` helper

**Files:**
- Modify: `src/harp/audio.py` (add module function near top, after imports)
- Modify: `src/harp/session.py` (`_bytes_to_float32` staticmethod, ~line 174-179)
- Test: `tests/test_audio.py`

**Interfaces:**
- Produces: `harp.audio.bytes_to_float32(buf: bytes) -> np.ndarray` — 16-bit PCM bytes → float32 in [-1, 1); empty buffer → empty array.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_audio.py`:

```python
import numpy as np

from harp.audio import bytes_to_float32


def test_bytes_to_float32_converts_int16_pcm():
    pcm = np.array([0, 32767, -32768], dtype=np.int16).tobytes()
    out = bytes_to_float32(pcm)
    assert out.dtype == np.float32
    assert out.shape == (3,)
    assert abs(out[0]) < 1e-6
    assert out[1] == np.float32(32767 / 32768.0)


def test_bytes_to_float32_empty():
    out = bytes_to_float32(b"")
    assert out.dtype == np.float32
    assert out.shape == (0,)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_audio.py::test_bytes_to_float32_converts_int16_pcm -v`
Expected: FAIL — `ImportError: cannot import name 'bytes_to_float32'`.

- [ ] **Step 3: Add the helper**

In `src/harp/audio.py`, after the imports and before `class AudioSource`:

```python
def bytes_to_float32(buf: bytes) -> "np.ndarray":
    """Convert 16-bit mono PCM bytes to a float32 array in [-1, 1)."""
    import numpy as np
    if not buf:
        return np.zeros(0, dtype=np.float32)
    ints = np.frombuffer(buf, dtype=np.int16)
    return ints.astype(np.float32) / 32768.0
```

- [ ] **Step 4: Point `HarpSession` at the shared helper**

In `src/harp/session.py`, replace the `_bytes_to_float32` staticmethod body with a delegation (keep the method so existing call sites `self._bytes_to_float32(chunk)` are untouched):

```python
    @staticmethod
    def _bytes_to_float32(buf: bytes) -> np.ndarray:
        from harp.audio import bytes_to_float32
        return bytes_to_float32(buf)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_audio.py tests/test_session.py -q`
Expected: PASS (new helper tests + unchanged session tests).

- [ ] **Step 6: Lint + commit**

```bash
uv run ruff check src tests
git add src/harp/audio.py src/harp/session.py tests/test_audio.py
git commit -m "refactor(audio): extract shared bytes_to_float32 helper"
```

---

## Task A2: `DictationSession` — buffer, then decode once

**Files:**
- Create: `src/harp/dictation.py`
- Test: `tests/test_dictation.py`

**Interfaces:**
- Consumes: `AudioSource` (protocol: `sample_rate`, `frames()`, `close()`), `bytes_to_float32` (A1), `TranscribeFn = Callable[[np.ndarray, Optional[str], Optional[str]], str]`.
- Produces:
  ```python
  DictationSession(audio, transcribe, language=None,
                   on_partial=None, max_seconds=120.0)
  ```
  Methods: `start() -> None`, `stop() -> str` (idempotent; returns final text), property `final_text -> str`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_dictation.py`:

```python
import threading

import numpy as np

from harp.dictation import DictationSession


class _ListSource:
    """Yields a fixed list of PCM frames, then ends. Deterministic."""

    def __init__(self, frames, sr=16000):
        self.sample_rate = sr
        self.channels = 1
        self._frames = list(frames)
        self.closed = False

    def frames(self):
        for f in self._frames:
            if self.closed:
                return
            yield f

    def close(self):
        self.closed = True


class _QueuedSource:
    """Queue-backed source mirroring MicrophoneSource: frames arrive over
    time; close() drops a None sentinel to end iteration after draining."""

    def __init__(self, sr=16000):
        import queue
        self.sample_rate = sr
        self.channels = 1
        self._q = queue.Queue()
        self.closed = False

    def push(self, frame):
        self._q.put(frame)

    def frames(self):
        while True:
            item = self._q.get()
            if item is None:
                return
            yield item

    def close(self):
        if self.closed:
            return
        self.closed = True
        self._q.put(None)


def _frame(samples):
    return np.zeros(samples, dtype=np.int16).tobytes()


def test_no_decode_while_recording_then_one_on_stop():
    calls = {"n": 0, "lens": []}

    def transcribe(audio, prompt, language):
        calls["n"] += 1
        calls["lens"].append(int(audio.shape[0]))
        return "hello world"

    src = _ListSource([_frame(1600)] * 3)
    d = DictationSession(src, transcribe)
    d.start()
    d._worker.join(timeout=5.0)   # source ends on its own
    assert calls["n"] == 0        # nothing decoded while buffering
    text = d.stop()
    assert text == "hello world"
    assert calls["n"] == 1        # exactly one decode, on stop
    assert calls["lens"] == [3 * 1600]   # whole clip


def test_stop_drains_queued_tail():
    got = {}

    def transcribe(audio, prompt, language):
        got["len"] = int(audio.shape[0])
        return "x"

    src = _QueuedSource()
    d = DictationSession(src, transcribe)
    d.start()
    for _ in range(5):
        src.push(_frame(1600))
    # stop() closes the source (sentinel) and must drain all 5 frames.
    d.stop()
    assert got["len"] == 5 * 1600


def test_empty_buffer_returns_empty_string():
    def transcribe(audio, prompt, language):
        raise AssertionError("must not decode an empty buffer")

    d = DictationSession(_ListSource([]), transcribe)
    d.start()
    assert d.stop() == ""


def test_stop_is_idempotent():
    def transcribe(audio, prompt, language):
        return "once"

    d = DictationSession(_ListSource([_frame(800)]), transcribe)
    d.start()
    assert d.stop() == "once"
    assert d.stop() == "once"          # no re-decode, same text
    assert d.final_text == "once"


def test_max_seconds_caps_the_buffer():
    lengths = []

    def transcribe(audio, prompt, language):
        lengths.append(int(audio.shape[0]))
        return ""

    # 10 frames of 1600 samples = 16000 samples = 1.0s; cap at 0.3s.
    src = _ListSource([_frame(1600)] * 10)
    d = DictationSession(src, transcribe, max_seconds=0.3)
    d.start()
    d._worker.join(timeout=5.0)
    d.stop()
    # capped near 0.3s (4800 samples); never the full 16000.
    assert lengths[0] <= 16000 * 0.3 + 1600
    assert lengths[0] < 10 * 1600
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_dictation.py -q`
Expected: FAIL — module `harp.dictation` does not exist.

- [ ] **Step 3: Implement `DictationSession`**

Create `src/harp/dictation.py`:

```python
"""DictationSession: full (record-then-transcribe) mode for bounded
push-to-talk utterances. Buffers audio while recording and decodes the whole
clip once on stop against an injected (warm) transcribe callable. Pure of
model/mic — unit-testable with a fake AudioSource and a fake transcribe."""
from __future__ import annotations

import threading
from typing import Callable, List, Optional

import numpy as np

from harp.audio import AudioSource, bytes_to_float32
from harp.streaming import TranscribeFn


class DictationSession:
    def __init__(
        self,
        audio: AudioSource,
        transcribe: TranscribeFn,
        language: Optional[str] = None,
        on_partial: Optional[Callable[[str], None]] = None,  # reserved, inert
        max_seconds: float = 120.0,
    ) -> None:
        self._audio = audio
        self._transcribe = transcribe
        self._language = language
        self._on_partial = on_partial  # v1: unused
        self._max_samples = int(max_seconds * audio.sample_rate)
        self._buf: List[bytes] = []
        self._worker: Optional[threading.Thread] = None
        self._started = False
        self._closed = False
        self._final_text = ""

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._worker = threading.Thread(
            target=self._run, name="dictation", daemon=True)
        self._worker.start()

    def _run(self) -> None:
        total = 0
        try:
            for chunk in self._audio.frames():
                self._buf.append(chunk)
                total += len(chunk) // 2  # bytes -> int16 samples
                if total >= self._max_samples:
                    break
        except Exception:  # pragma: no cover - worker must not raise out
            pass
        finally:
            # On the max-seconds cap (or any early exit) stop capture so the
            # source's queue can't keep growing. Idempotent with stop().
            try:
                self._audio.close()
            except Exception:  # pragma: no cover
                pass

    @property
    def final_text(self) -> str:
        return self._final_text

    def stop(self) -> str:
        if self._closed:
            return self._final_text
        self._closed = True
        # Closing the source ends the worker's frames() loop (mic: via its
        # None sentinel, draining everything captured; file: already ending).
        try:
            self._audio.close()
        except Exception:  # pragma: no cover
            pass
        if self._worker is not None:
            self._worker.join(timeout=5.0)
        pcm = b"".join(self._buf)
        if not pcm:
            self._final_text = ""
            return ""
        audio = bytes_to_float32(pcm)
        self._final_text = (self._transcribe(
            audio, None, self._language) or "").strip()
        return self._final_text
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_dictation.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check src tests
git add src/harp/dictation.py tests/test_dictation.py
git commit -m "feat(dictation): DictationSession — buffer then decode once"
```

---

## Task A3: Export + real-model integration test

**Files:**
- Modify: `src/harp/__init__.py`
- Test: `tests/test_dictation.py` (append a slow integration test)

**Interfaces:**
- Produces: `from harp import DictationSession`.

- [ ] **Step 1: Export it**

In `src/harp/__init__.py`, add the import and `__all__` entry:

```python
from harp.dictation import DictationSession
```
and add `"DictationSession",` to `__all__` (keep alphabetical).

- [ ] **Step 2: Write the integration test**

Append to `tests/test_dictation.py`:

```python
import pytest
from pathlib import Path

from tests.fakes import FileAudioSource


@pytest.mark.slow
def test_dictation_transcribes_real_wav():
    from harp.whisper import LocalWhisperEngine

    wav = Path("tests/assets/ground_truth.wav")
    eng = LocalWhisperEngine(
        model_size="base", device="cpu", compute_type="default", beam_size=1)
    d = DictationSession(FileAudioSource(wav), eng.transcribe)
    d.start()
    d._worker.join(timeout=120.0)
    text = d.stop()
    assert len(text) > 50
    assert "existence" in text.lower()
```

- [ ] **Step 3: Run unit tests (import path) + the integration test**

Run: `uv run pytest tests/test_dictation.py -q` (unit tests still pass with the new import)
Run: `uv run pytest tests/test_dictation.py -q -m slow` (real model; slow)
Expected: PASS.

- [ ] **Step 4: Full suite + lint + commit**

```bash
uv run pytest -q
uv run ruff check src tests
git add src/harp/__init__.py tests/test_dictation.py
git commit -m "feat(dictation): export DictationSession + real-model integration test"
```

---

## Task A4: Release `harpio`

**Files:**
- Modify: `pyproject.toml` (version)

- [ ] **Step 1: Bump version**

In `pyproject.toml`, set `version = "0.10.0"` (new minor — additive public API).

- [ ] **Step 2: Commit + tag + publish**

```bash
git add pyproject.toml
git commit -m "chore(release): v0.10.0 — DictationSession"
git tag v0.10.0
git push origin main --tags
```

Publish per the repo's usual release path (the maintainer/`github-repos` release flow builds and uploads the wheel to PyPI). Confirm `harpio==0.10.0` is installable before starting Phase B, or Phase B can develop against the editable local harp and only require the release before aegis is released.

---

# PHASE B — aegis: consume `DictationSession`

## Task B1: Rewrite the aegis voice session for full mode

**Files:**
- Modify: `src/aegis/voice/session.py` (`_default_factory`, `VoiceSession`; keep `_get_engine`, `prewarm`, `_ENGINE_CACHE`)
- Test: `tests/test_voice_factory.py`, `tests/test_voice_session.py`

**Interfaces:**
- Produces: `_default_factory(cfg) -> DictationSession` built with the warm engine.
- Produces: `VoiceSession(cfg, on_final, _session_factory=None)` — `start()` begins recording; `stop()` runs the decode off-thread and calls `on_final(text)` from that worker thread; `is_running` property.

- [ ] **Step 1: Update the factory test**

In `tests/test_voice_factory.py`, replace the `_SpyHarpSession` usage: the factory now builds a `DictationSession`. Patch `harp.DictationSession` instead of `harp.HarpSession`, drop the `transcribe_segments`/`warmup` assertions (obsolete), and assert the engine pins remain. Concretely, change `_patch` to also patch `DictationSession`:

```python
class _SpyDictation:
    calls = []

    def __init__(self, audio, transcribe, **kwargs):
        _SpyDictation.calls.append({"transcribe": transcribe, **kwargs})
        self.audio = audio
```

In `_patch(monkeypatch)`:
```python
    _SpyDictation.calls = []
    monkeypatch.setattr(harp, "DictationSession", _SpyDictation, raising=False)
```

Replace `test_factory_disables_warmup` and `test_factory_passes_transcribe_segments` with:

```python
def test_factory_builds_dictation_session(monkeypatch):
    _patch(monkeypatch)
    session = vs._default_factory(VoiceConfig(model="base"))
    assert isinstance(session, _SpyDictation)
    assert callable(_SpyDictation.calls[-1]["transcribe"])


def test_factory_passes_language(monkeypatch):
    _patch(monkeypatch)
    vs._default_factory(VoiceConfig(model="base", language="es"))
    assert _SpyDictation.calls[-1].get("language") == "es"
```

Keep `test_engine_is_cached_across_recordings`, `test_engine_pins_cpu_default_to_avoid_fallback_prints`, and the two `prewarm` tests unchanged.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_voice_factory.py -q`
Expected: FAIL — `_default_factory` still builds `HarpSession`; `harp.DictationSession` patch target may not exist yet on old harp.

- [ ] **Step 3: Rewrite `_default_factory`**

In `src/aegis/voice/session.py`, replace `_default_factory` with:

```python
def _default_factory(cfg: VoiceConfig):
    """Build a full-mode DictationSession: record while active, decode the
    whole clip once on stop against the warm engine. Imports harp lazily."""
    from harp import DictationSession, MicrophoneSource

    engine = _get_engine(cfg)
    return DictationSession(
        audio=MicrophoneSource(),
        transcribe=engine.transcribe,
        language=cfg.language,
    )
```

- [ ] **Step 4: Rewrite `VoiceSession`**

Replace the `VoiceSession` class (keep the module docstring accurate) with:

```python
class VoiceSession:
    """Drives a DictationSession: start() records; stop() decodes the buffered
    clip off-thread and delivers the final text via on_final. UI-agnostic and
    testable with a stub DictationSession (no model, no mic)."""

    def __init__(
        self,
        cfg: VoiceConfig,
        on_final: Callable[[str], None],
        _session_factory: Optional[Callable[[VoiceConfig], object]] = None,
    ) -> None:
        self._cfg = cfg
        self._on_final = on_final
        self._factory = _session_factory or _default_factory
        self._session: object | None = None
        self._recording = False
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        return self._recording

    def start(self) -> None:
        with self._lock:
            if self._recording:
                return
            self._session = self._factory(self._cfg)
            self._session.start()
            self._recording = True

    def stop(self) -> None:
        with self._lock:
            if not self._recording:
                return
            self._recording = False
            session = self._session
            self._session = None

        def _finish() -> None:
            try:
                text = session.stop()
            except Exception:
                text = ""
            self._on_final(text or "")

        threading.Thread(
            target=_finish, name="voice-decode", daemon=True).start()
```

Update the module docstring's first line to: `"""VoiceSession: drives a harp DictationSession and delivers the final transcript through a callback."""`. Remove the now-unused `Callable[[str, str], None]` type note if present.

- [ ] **Step 5: Rewrite the session unit tests**

Replace `tests/test_voice_session.py` with full-mode tests:

```python
import threading
import time

from aegis.config import VoiceConfig
from aegis.voice.session import VoiceSession


class _FakeDictation:
    def __init__(self, text="hello world"):
        self._text = text
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True
        return self._text


def test_start_then_stop_delivers_final_text():
    fake = _FakeDictation("hello world")
    finals = []
    vs = VoiceSession(VoiceConfig(), on_final=finals.append,
                      _session_factory=lambda cfg: fake)
    vs.start()
    assert vs.is_running is True and fake.started is True
    vs.stop()
    deadline = time.time() + 2
    while not finals and time.time() < deadline:
        time.sleep(0.01)
    assert finals == ["hello world"]
    assert vs.is_running is False and fake.stopped is True


def test_stop_without_start_is_noop():
    finals = []
    vs = VoiceSession(VoiceConfig(), on_final=finals.append,
                      _session_factory=lambda cfg: _FakeDictation())
    vs.stop()   # must not raise, must not deliver
    assert finals == []


def test_decode_error_delivers_empty_string():
    class _Boom(_FakeDictation):
        def stop(self):
            raise RuntimeError("decode failed")

    finals = []
    vs = VoiceSession(VoiceConfig(), on_final=finals.append,
                      _session_factory=lambda cfg: _Boom())
    vs.start()
    vs.stop()
    deadline = time.time() + 2
    while not finals and time.time() < deadline:
        time.sleep(0.01)
    assert finals == [""]
```

- [ ] **Step 6: Run + lint + commit**

Run: `uv run pytest tests/test_voice_factory.py tests/test_voice_session.py -q`
Expected: PASS.

```bash
uv run ruff check src/aegis/voice/
git add src/aegis/voice/session.py tests/test_voice_factory.py tests/test_voice_session.py
git commit -m "feat(voice): full-mode VoiceSession over DictationSession"
```

---

## Task B2: Simplify the aegis app voice wiring

**Files:**
- Modify: `src/aegis/tui/app.py` (`action_toggle_voice`, remove `_on_voice_update`, adjust `_apply_voice_text`/`_stop_voice`)
- Test: `tests/test_voice_action.py`

**Interfaces:**
- Consumes: `VoiceSession(cfg, on_final, _session_factory)` (B1).
- The final text is inserted **once** at the origin input on stop; the target pane + base text are captured per-recording in the `on_final` closure so a late decode always lands on the right input.

- [ ] **Step 1: Update the action test**

In `tests/test_voice_action.py`, the stub no longer takes `on_update`. Replace `_StubVoice` with a full-mode stub and adjust the streaming assertions:

```python
class _StubVoice:
    last = None

    def __init__(self, cfg, on_final, **_):
        self.cfg = cfg
        self.on_final = on_final
        self._running = False
        _StubVoice.last = self

    @property
    def is_running(self):
        return self._running

    def start(self):
        self._running = True

    def stop(self):
        self._running = False
        # deliver synchronously for the test
        self.on_final("hello world")
```

Rewrite the streaming test to a single-insert-on-stop test:

```python
@pytest.mark.asyncio
async def test_stop_inserts_final_text_once(monkeypatch):
    monkeypatch.setattr("aegis.tui.app.voice_available", lambda: True)
    app = _app(voice=VoiceConfig(enabled=True))
    app._voice_session_factory = _StubVoice
    async with app.run_test() as pilot:
        pane = app._active
        pane.input_widget().value = "prefix "
        await app.action_toggle_voice()      # start
        assert pane.has_class("recording")
        await app.action_toggle_voice()      # stop -> on_final("hello world")
        await pilot.pause()
        assert pane.input_widget().value == "prefix hello world"
        assert not pane.has_class("recording")
```

Keep `test_second_toggle_stops_and_clears` (adjust: after stop, `app._voice is None` and indicator cleared) and `test_unavailable_deps_shows_hint_no_session` (unchanged; stub takes `on_final`).

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_voice_action.py -q`
Expected: FAIL — app still constructs `VoiceSession(cfg, on_update, on_final)` and defines `_on_voice_update`.

- [ ] **Step 3: Rewrite `action_toggle_voice` + insertion**

In `src/aegis/tui/app.py`, replace `action_toggle_voice` and the voice callbacks with:

```python
    async def action_toggle_voice(self) -> None:
        if self._voice is not None:
            self._stop_voice()
            return
        if not voice_available():
            self.notify(unavailable_reason(), severity="warning")
            return
        pane = self._active
        if not isinstance(pane, ConversationPane):
            return
        base = pane.input_widget().value

        def on_final(text: str, pane=pane, base=base) -> None:
            # Fires from the decode worker thread -> marshal onto the UI loop.
            self._marshal(self._apply_voice_text, pane, base, text)

        try:
            self._voice = self._voice_session_factory(self._voice_cfg, on_final)
            self._voice.start()
        except Exception as exc:  # noqa: BLE001 — mic/model open failure
            self._voice = None
            self.notify(f"voice failed: {exc}", severity="error")
            return
        self._voice_pane = pane
        pane.set_recording(True)

    def _apply_voice_text(self, pane, base: str, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        joiner = "" if (not base or base.endswith((" ", "\n"))) else " "
        pane.input_widget().value = base + joiner + text

    def _marshal(self, fn, *args) -> None:
        loop = self._loop
        if loop is None:
            fn(*args)
        else:
            loop.call_soon_threadsafe(fn, *args)

    def _stop_voice(self) -> None:
        voice, pane = self._voice, self._voice_pane
        self._voice = None
        self._voice_pane = None
        if pane is not None:
            pane.set_recording(False)
        if voice is not None:
            voice.stop()   # non-blocking; decode + insert happen off-thread
```

Delete `_on_voice_update` and `_on_voice_final` (replaced by the per-recording `on_final` closure). Remove the now-unused `self._voice_base` instance attribute from `__init__` (keep `self._voice_pane` for the indicator).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_voice_action.py -q`
Expected: PASS.

- [ ] **Step 5: Full suite + lint + commit**

```bash
uv run pytest -q -m "not live"
uv run ruff check src/
git add src/aegis/tui/app.py tests/test_voice_action.py
git commit -m "feat(voice): single-insert-on-stop wiring for full mode"
```

---

## Task B3: Bump the `harpio` pin + docs

**Files:**
- Modify: `pyproject.toml` (`voice` extra)
- Modify: `docs/configuration.md` (drop the `preview` knob mention if present)

- [ ] **Step 1: Bump the pin**

In `pyproject.toml`, set the voice extra to `harpio>=0.10.0` (needs `DictationSession`).

- [ ] **Step 2: Trim obsolete docs**

In `docs/configuration.md`, remove the `preview:` line from the `voice:` example and its explanation (full mode has no transient preview in v1). Leave `enabled`, `model`, `key`, `language`.

- [ ] **Step 3: Verify + commit**

Run: `uv pip install -e '.[voice]'` (resolves `harpio>=0.10.0`)
Run: `uv run python -c "from harp import DictationSession; print('ok')"`

```bash
git add pyproject.toml docs/configuration.md
git commit -m "chore(voice): require harpio>=0.10.0; drop preview knob"
```

---

## Self-Review

**Spec coverage:**
- Two explicit modes; new `DictationSession` in harp → Task A2/A3.
- Buffer while recording, decode once on stop → A2 (`_run` no decode; `stop()` one transcribe).
- Stop drains full buffer (no tail loss) → A2 `test_stop_drains_queued_tail` (relies on the landed MicrophoneSource drain fix).
- Injected warm transcribe, no warmth machinery in harp → A2 signature; aegis `_get_engine`/`prewarm` kept → B1.
- `on_partial` reserved/inert, `max_seconds` cap → A2 (`test_max_seconds_caps_the_buffer`).
- aegis rewrite: DictationSession factory, single insert on stop, off-thread decode, delete streaming plumbing → B1/B2.
- Kept: prewarm, cpu/default + log-silencing, config, packaging, feature-detect → B1 (`_get_engine`/`prewarm` untouched), B3.
- Dropped: warmup/transcribe_segments/transient → B1 factory rewrite.
- Error handling (empty buffer, decode failure, teardown) → A2 (`test_empty_buffer...`), B1 (`test_decode_error...`), B2 (`_stop_voice` on teardown path already called from `action_quit`).
- Testing (fakes, no model/mic; real-model integration) → A2/A3/B1/B2.
- Rollout harp-first + release → A4, B3.

**Placeholder scan:** none — every code step is complete.

**Type consistency:** `DictationSession(audio, transcribe, language=, on_partial=, max_seconds=)` identical across A2/A3/B1; `VoiceSession(cfg, on_final, _session_factory=)` identical across B1/B2; `_apply_voice_text(pane, base, text)` matches its `on_final` closure call; `bytes_to_float32` name consistent A1↔A2.

**Known adaptation points for the executor:**
- harp release/publish (A4) follows the maintainer's usual PyPI flow; if developing Phase B before the release lands, install the editable local harp into the aegis venv and defer the pin bump (B3) verification until `0.10.0` is on PyPI.
- `action_quit` already calls `_stop_voice()` when `self._voice is not None` — no change needed there; `_stop_voice` is now non-blocking.
- v1 edge: pressing the toggle again during the sub-second decode of a prior utterance starts a new recording; the prior decode still lands on its captured pane/base via the closure. Acceptable; documented.
