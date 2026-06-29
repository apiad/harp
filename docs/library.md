# Harp as a library

`harp` is primarily a Python library. The terminal client (`harp start`,
`harp transcribe`) is one of several possible consumers; you can drive a
`HarpSession` from any Python code.

## Quickstart

```python
from harp import HarpSession, FileSource
from harp.vad import SileroDetector
from harp.whisper import LocalWhisperEngine

engine = LocalWhisperEngine(model_size="base", compute_type="int8", beam_size=1)
with HarpSession(
    audio=FileSource("meeting.m4a"),
    transcribe=engine.transcribe,
    detector=SileroDetector(),
) as session:
    for event in session.events():
        # committed is append-only; transient is the in-progress guess
        print(event.committed, "|", event.transient)
    print("final:", session.final_text)
```

`HarpSession.events()` blocks on the calling thread and yields a
[`TranscriptEvent`](#transcriptevent) each time the committed or transient text
changes. A terminal `is_final` event lands last. Iteration ends when the session
ends (audio exhausted or `session.stop()` called from another thread).

## API

### `HarpSession`

```python
HarpSession(
    audio: AudioSource,
    transcribe: Callable[[np.ndarray, Optional[str], Optional[str]], str],
    detector: SpeechDetector | None = None,   # None -> NullDetector (force-cuts only)
    slide_interval: float = 1.0,              # step cadence, in seconds of audio fed
    warmup: float = 10.0,                     # buffer before chunked mode
    silence_threshold: float = 0.5,           # trailing silence that finalizes a chunk
    max_segment: float = 25.0,                # force-cut length when no pause
    language: Optional[str] = None,
    transient: bool = False,                  # live preview (costs ~2-4x; off = real-time)
)
```

* `audio` — any [`AudioSource`](#audiosource) implementation.
* `transcribe` — a function compatible with `harp.streaming.TranscribeFn`.
  Pass `LocalWhisperEngine(...).transcribe` for the bundled engine.
* `detector` — a [`SpeechDetector`](#speechdetector); pass `SileroDetector()`
  for VAD-based chunk boundaries.
* `transient` — leave `False` for real-time finalize-only streaming; set `True`
  for a live word-by-word preview (re-decodes the in-progress chunk).

Methods: `events() -> Iterator[TranscriptEvent]`, `stop() -> None`,
`final_text -> str`. Use as a context manager.

### `TranscriptEvent`

```python
@dataclass(frozen=True)
class TranscriptEvent:
    committed: str   # cumulative finalized text — append-only, never revised
    transient: str   # in-progress hypothesis — may change or be emptied
    is_final: bool   # True only on the terminal flush
    ts: float        # monotonic seconds since session start

    @property
    def text(self) -> str:    # committed + transient, stripped
        ...
    @property
    def words(self) -> int:   # word count of text
        ...
```

### `AudioSource`

```python
class AudioSource(Protocol):
    sample_rate: int
    channels: int
    def frames(self) -> Iterable[bytes]: ...   # 16-bit PCM mono
    def close(self) -> None: ...
```

Bundled implementations: `MicrophoneSource`, `FileSource`. Implement your own —
e.g. a `WebSocketAudioSource` that yields PCM frames received over a network
connection.

### `SpeechDetector`

```python
class SpeechDetector(Protocol):
    def speech_segments(self, audio: np.ndarray) -> list[tuple[int, int]]: ...
```

Bundled implementations: `SileroDetector` (Silero VAD), `NullDetector`
(reports no speech → engine force-cuts at `max_segment`).

## Driving from asyncio

`HarpSession` is sync; in an asyncio app, run it in an executor:

```python
import asyncio

async def dictate(ws):
    with HarpSession(audio=WebSocketAudioSource(ws), transcribe=engine.transcribe,
                     detector=SileroDetector()) as s:
        loop = asyncio.get_running_loop()
        def pump():
            for ev in s.events():
                asyncio.run_coroutine_threadsafe(
                    ws.send_json({"committed": ev.committed, "transient": ev.transient}),
                    loop,
                )
        await loop.run_in_executor(None, pump)
        await ws.send_json({"final": s.final_text})
```
