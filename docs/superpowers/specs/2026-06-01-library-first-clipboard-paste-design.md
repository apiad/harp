---
title: Library-first harp with clipboard-paste delivery
date: 2026-06-01
status: approved
version_target: 0.7.0
supersedes:
  - docs/superpowers/specs/2026-05-18-streaming-backpatch-dictation-design.html
---

# Library-first harp with clipboard-paste delivery

## Goal

Reshape harp so the **library is primary** and the CLI / TUI is one of several
possible clients. At the same time, change how transcribed text reaches the
focused application: the terminal becomes the live (back-patched) preview
surface, and the focused window receives the session's text **exactly once**,
via clipboard + a synthesized `Ctrl+V`. No keystrokes hit the target app
between session start and the final paste.

This unblocks downstream consumers (e.g. a web app feeding browser-captured
audio over a WebSocket) without forcing them to depend on Rich, `uinput`,
`wl-copy`, or `evdev`.

## Non-goals

Explicitly out of scope for v0.7.0 — call out so they don't drift in during
implementation:

- Mid-session paragraph breaks or partial pastes. Exactly one paste per
  session, at end. (Deferred: Slice B.)
- VAD-driven auto-stop. (TASKS.md `#10`.)
- Post-processing hooks. (TASKS.md `#9` / Slice D.)
- macOS / X11 clipboard or input paths.
- A `WebSocketAudioSource` implementation. The library will accept one when
  the consumer needs it; harp doesn't ship it.
- Splitting harp into multiple installable packages. We use an `[cli]`
  optional-dependencies extra; no separate distribution.

## Library API

The public surface lives at the top level of the `harp` package:

```python
from harp import HarpSession, MicrophoneSource, CommitEvent
```

### Audio source

```python
class AudioSource(Protocol):
    sample_rate: int          # e.g. 16_000
    channels: int             # 1

    def frames(self) -> Iterable[bytes]:
        """Yield PCM int16 frames until the source is exhausted or closed.

        Each yielded chunk is a contiguous bytes buffer of int16 samples at
        ``sample_rate``. Frame size is the source's choice; the session
        rebuffers internally for the decode loop.
        """

    def close(self) -> None:
        """Stop producing frames and release OS resources. Idempotent."""
```

One implementation ships in v0.7.0:

- **`MicrophoneSource`** — wraps `sounddevice.InputStream` at 16 kHz mono.
  Constructor takes an optional `device` (sounddevice device name/index).
  `frames()` yields chunks as they arrive from the audio callback; `close()`
  stops the stream.

A second, **test-only** implementation lives under `tests/` (not exported):

- **`FileAudioSource`** — reads a WAV file, yields it in realistic-sized
  chunks with controllable pacing. Used for the library and integration
  tests in place of a real microphone.

### Session

```python
class HarpSession:
    def __init__(
        self,
        audio: AudioSource,
        model: str = "base",            # whisper model name
        slide_interval: float = 1.0,    # seconds between re-decodes
        device: str = "auto",           # "auto" | "cpu" | "cuda"
    ) -> None: ...

    def __enter__(self) -> "HarpSession": ...
    def __exit__(self, *exc) -> None: ...

    def events(self) -> Iterator[CommitEvent]:
        """Yield CommitEvents as the committed prefix grows or is revised.

        Blocks on the producer thread. Exits when ``stop()`` is called or
        the audio source is exhausted. After exit, ``final_text`` is
        populated.
        """

    def stop(self) -> None:
        """Signal the session to finalize and drain. Thread-safe."""

    @property
    def final_text(self) -> str:
        """The committed prefix at session end. Empty string if no commits."""
```

Implementation notes:

- The decode loop runs on a worker thread (kept from the existing daemon).
  `events()` reads from a `queue.Queue` populated by the worker. `stop()`
  flips a flag the worker checks at the top of each slide.
- The context manager loads the Whisper model on `__enter__` and releases
  it on `__exit__`. The audio source's `close()` is called on exit too,
  whether or not the caller already stopped the session.
- LocalAgreement-2 state, the bounded buffer trim, and `slide_interval`
  semantics are **preserved as-is** from the v0.6.0 streaming work. This
  spec moves them, it does not redesign them.

### Event

```python
@dataclass(frozen=True)
class CommitEvent:
    text: str       # full current committed prefix
    words: int      # word count of ``text``
    ts: float       # monotonic seconds since session start
```

Every event carries the **full** committed prefix. There is no separate
"revision" event: clients that care about deltas (back-patch awareness for
a UI) compute them by diffing against the prior event's `text`. This keeps
the event protocol trivial and the wire format (for a web client) tiny.

There is **no** explicit "session ended" event. The iterator exiting is
the end signal; `final_text` is the result.

### Library usage example

```python
from harp import HarpSession, MicrophoneSource

with HarpSession(audio=MicrophoneSource(), model="base") as session:
    for event in session.events():
        print(event.text)             # ← live preview here
    print("final:", session.final_text)
```

A web-app sketch (not shipped; just to show the shape is right):

```python
@app.websocket("/dictate")
async def dictate(ws):
    src = WebSocketAudioSource(ws)             # caller-provided
    loop = asyncio.get_running_loop()
    with HarpSession(audio=src, model="base") as session:
        def pump():
            for event in session.events():
                asyncio.run_coroutine_threadsafe(
                    ws.send_json({"text": event.text}), loop,
                )
        await loop.run_in_executor(None, pump)
        await ws.send_json({"final": session.final_text})
```

## CLI / TUI client

A new module `harp.cli` houses everything OS- and presentation-specific.
Nothing in the library imports from `harp.cli`.

### Components

- **`harp.cli.hotkey`** — `evdev` watcher for `Ctrl+Space`. Owns the lifecycle:
  on press (or first press in toggle mode), constructs a `MicrophoneSource`
  and a `HarpSession`, enters its context, and starts iterating events on a
  worker thread. On release (or second press), calls `session.stop()`. After
  the iterator drains, invokes `ClipboardSink.deliver(session.final_text)`.
- **`harp.cli.display`** — `TerminalDisplay` subscribes to the event iterator
  on the main thread. Renders a Rich `Live` panel: body is the current
  committed prefix; footer is `(listening… {N} words)`. When the iterator
  exits, closes the `Live` panel and prints the final text as a normal line
  (or `(empty)` if nothing was committed).
- **`harp.cli.clipboard`** — `ClipboardSink`:
  1. Snapshot existing clipboard via `wl-paste --no-newline` (capture stdout;
     empty result is fine).
  2. Write `final_text` via `wl-copy`.
  3. If `--paste`: synthesize `Ctrl+V` via `uinput`, wait 200 ms for the app
     to consume it.
  4. Restore the snapshot via `wl-copy` (or `wl-copy --clear` if the snapshot
     was empty).

The display and the hotkey watcher coordinate so the Rich `Live` panel and
the session iterator both run cleanly: the hotkey worker reads events off a
queue; the display polls the same queue (or a `tee`'d copy) on the main
thread. Exact threading shape is an implementation detail of the plan.

### CLI flag changes

| Flag | Change |
|---|---|
| `--type` | **Removed.** Live typing into the focused app is what we're killing. |
| `--copy` | **Removed.** Clipboard is now the delivery channel, not a side-effect. |
| `--paste` / `--no-paste` | **New**, default `--paste`. Off = clipboard only; user pastes manually. |
| `--toggle`, `--full`, `--slide`, `--device` | Unchanged. |

`HarpConfig` keeps `stream_slide_interval`; any `stream_*` keys tied to the
removed live-typing pacer (back-patch pause, type-defer, etc.) are deleted.

### Failure modes

- **`wl-copy` / `wl-paste` missing** — `ClipboardSink` logs a warning at
  daemon start, marks itself unhealthy, and forces `--no-paste` behavior.
  The terminal panel surfaces a one-line note. No silent degradation.
- **`uinput` permission missing** (with `--paste`) — same: warn at start,
  force `--no-paste`, surface in panel.
- **Focused window doesn't accept `Ctrl+V`** — out of scope; harp's
  responsibility ends at synthesizing the keystroke.
- **User alt-tabs mid-session** — documented: paste lands wherever focus
  is at release. Mitigation deferred.
- **Empty session (zero commits)** — no clipboard write, no paste, no
  clipboard restore. Panel closes and prints `(empty)`.

## Package layout

```
src/harp/
  __init__.py            # exports: HarpSession, MicrophoneSource, CommitEvent, AudioSource
  session.py             # HarpSession + worker thread
  events.py              # CommitEvent
  audio.py               # AudioSource Protocol + MicrophoneSource
  transcription.py       # whisper + LocalAgreement-2 (refactored from existing)
  models.py              # model download/list/path management

src/harp/cli/
  __init__.py
  main.py                # Typer app — entry point: harp = harp.cli.main:app
  display.py             # TerminalDisplay (Rich Live)
  clipboard.py           # ClipboardSink (wl-copy / wl-paste / uinput Ctrl+V)
  hotkey.py              # Ctrl+Space evdev watcher → session lifecycle
```

`pyproject.toml` gains an extra:

```toml
[project.optional-dependencies]
cli = ["rich", "typer", "evdev", "python-uinput"]
```

The default install of `harpio` still pulls the CLI extra (so end-user
behavior is unchanged). Library-only consumers can install with
`pip install harpio[lib]` once we publish a `lib` extra that excludes the
CLI deps — but that's a packaging follow-up, not part of v0.7.0.

### Deletions

- `IncrementalTyper`'s per-token type+backspace loop (and the class itself
  if no other call sites survive).
- `--type` and `--copy` flag handling + their config keys.
- TASKS.md cleanup: `#7 Local Whisper` (shipped in v0.5.0), `#8 Prompt
  Presets` (obsolete since command mode was removed in v0.6.0).

## Testing

### Library tests

- **`HarpSession` against `FileAudioSource`** — drive a known WAV through a
  session, assert the event sequence is monotonically extending the
  committed prefix (modulo LocalAgreement-2 revisions), assert
  `final_text` matches the expected transcription.
- **`session.stop()` from another thread** — start a session, sleep, call
  `stop()` from a second thread, assert the event iterator exits and
  `final_text` is populated.
- **Empty audio source** — `FileAudioSource` yielding nothing → events
  iterator yields nothing → `final_text == ""`.

### CLI tests

- **`ClipboardSink` save/write/paste/restore** — mock `wl-copy`, `wl-paste`,
  and the `uinput` keystroke emitter; assert the four-step sequence and
  the restored-clipboard payload for both populated and empty initial
  clipboard.
- **`ClipboardSink` fallback** — `wl-copy` missing on PATH → sink reports
  unhealthy and `--paste` is ignored.
- **Hotkey state machine** — hold and toggle paths each fire `start` and
  `stop` against a fake session in the correct order.
- **End-to-end integration** (`tests/test_voice_integration.py`,
  re-shaped from the existing voice-integration test) — wire a
  `FileAudioSource` into the CLI's session path, run a full session,
  assert (a) clipboard contains expected text at end, (b) **zero** typed
  keystrokes between session start and end, (c) **exactly one** `Ctrl+V`
  keystroke at end.

### Manual smoke (verifies "Ctrl+Space works")

On zion, with a mic and a focused text field:

```bash
harp start --toggle
```

Press `Ctrl+Space`, speak a sentence, press `Ctrl+Space` again. Confirm:

1. Terminal `Live` panel showed the prefix growing in real time, including
   any back-patch revisions visible in the terminal.
2. The focused text field received **one** clean paste — no per-word
   keystrokes, no visible backspaces.
3. Clipboard contents after the session match what was just typed
   (regardless of what was on the clipboard before).
4. Pre-session clipboard contents are restored ~200 ms after the paste.

## Versioning & changelog

Bump to **v0.7.0**. CHANGELOG entry under "Changed" (behavior break) and
"Added" (library API):

> **Changed**
> - Dictation no longer types live into the focused window. The terminal
>   now shows the live (back-patched) transcription; the focused window
>   receives the session's final text once via clipboard + Ctrl+V at
>   session end. `--type` and `--copy` flags removed. New `--paste` /
>   `--no-paste` flag (default `--paste`).
>
> **Added**
> - Public Python API: `harp.HarpSession`, `harp.MicrophoneSource`,
>   `harp.CommitEvent`, `harp.AudioSource`. The CLI is now one of several
>   possible clients of the library. See `docs/library.md`.

A short `docs/library.md` is part of this slice, covering the API surface
and the library usage example above.

## Risks

- **Refactor scope underestimated.** The existing daemon mingles
  transcription, output, hotkey, and config. Extracting `HarpSession`
  cleanly may surface tangles. Mitigation: the plan stage greps the
  current `daemon.py` and `transcription.py` for cross-cutting state
  before committing to slice boundaries.
- **Threading.** The new shape has at least three threads: audio capture
  (sounddevice callback), decode loop, hotkey watcher; plus the main
  thread driving the Rich `Live` panel. The plan must spell out which
  thread owns which queue, and where `stop()` is observed.
- **Clipboard restore race.** If the user manually copies something during
  the 200 ms window between paste and restore, the restore clobbers their
  copy. Acceptable: it's a 200 ms window and the existing `--copy`
  behavior had the same shape. Note in the changelog.
