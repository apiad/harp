# Harp as a library

`harp` is primarily a Python library. The terminal client (`harp start`) is
one of several possible consumers; you can drive a `HarpSession` from any
Python code.

## Quickstart

```python
from harp import HarpSession, MicrophoneSource
from harp.whisper import LocalWhisperEngine

engine = LocalWhisperEngine(model_size="base")
with HarpSession(audio=MicrophoneSource(), transcribe=engine.transcribe) as session:
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
