# Internal Architecture

Harp is a local-first streaming transcription **engine** with thin front-ends.
The engine emits events; front-ends (the CLI, or any Python consumer) decide
how to present them. Audio never leaves the machine.

## Data flow

```
AudioSource ──frames(bytes)──▶ HarpSession ──feed/step──▶ StreamingTranscriber
                                    │                          │ uses
                                    │                          ├─ transcribe()  (LocalWhisperEngine)
                                    │                          └─ SpeechDetector (SileroDetector / NullDetector)
                                    ▼
                              TranscriptEvent(committed, transient, is_final)
                                    │
                                    ▼
                       consumer: TerminalDisplay / clipboard / -o file / your app
```

## The streaming engine (`harp.streaming.StreamingTranscriber`)

Pure and I/O-free: it receives a `transcribe` callable and a `SpeechDetector`,
so it is fully testable without loading any model.

1. **Warm-up.** While less than `warmup` seconds (default 10) of audio has been
   fed, the engine only buffers. A short utterance that ends here becomes a
   single clean decode at `finalize()` — exactly like classic push-to-talk
   dictation.
2. **Chunked streaming.** Past warm-up, on each `step()` the engine runs the VAD
   on the *active buffer* (audio since the last boundary). When a **trailing
   silence ≥ `silence_threshold`** follows the last speech segment, it
   **finalizes** that chunk: decodes it **once** (with the last 200 chars of
   committed text as `initial_prompt`), appends the text to the append-only
   `committed` string, and **drops the chunk's audio**. A chunk that grows past
   `max_segment` with no pause is force-cut.
3. **Transient preview (optional).** When `transient=True`, a non-finalizing
   `step()` re-decodes the bounded active buffer to produce a live preview.
   This is opt-in because re-decoding the in-progress chunk costs ~2–4× and is
   what blocks real-time on CPU. Default off (finalize-only).

**Why this is real-time.** Finalized audio is dropped and never re-decoded, so
per-step cost is bounded by `max_segment`. In finalize-only mode each chunk is
decoded exactly once → decode work ≈ 1× audio. Measured RTF ≈ 0.34 on `base`/CPU
(int8, beam 1) — ~3–4× faster than real-time, so lag cannot accumulate.

**Overlap finalization.** A fixed-window force-cut lands mid-word, which garbles
weak models and corrupts the commit seam. When a segment-aware decoder
(`transcribe_segments`) is supplied, the engine commits chunks by **absolute
segment timestamp** (exact overlap dedup) and **holds back** the trailing
`overlap` seconds — that mid-word tail is re-decoded with full context in the
next chunk instead of being committed cold. Repetition hallucinations (segment
compression ratio > 2.4, Whisper's own failed-decode signal) are dropped.

## The session (`harp.session.HarpSession`)

Drives the engine on a worker thread and yields `TranscriptEvent`s through a
queue. The **step cadence is driven by audio-time fed, not wall-clock** — a file
source delivers audio faster than real-time, and a wall-clock gate would let the
whole file arrive before the first step, collapsing the stream into one batch
decode. Counting fed samples makes the cadence identical for a real-time mic and
a fast file. `stop()` is thread-safe and idempotent.

## The event (`harp.events.TranscriptEvent`)

```python
@dataclass(frozen=True)
class TranscriptEvent:
    committed: str   # cumulative finalized text — append-only, never revised
    transient: str   # in-progress hypothesis — may change or be emptied
    is_final: bool   # True only on the terminal flush
    ts: float
```

Consumers render `committed` "in the dark" and `transient` "in the light". A
terminal `is_final` event always lands last.

## Audio sources (`harp.audio`)

`AudioSource` is a `Protocol` (`sample_rate`, `channels`, `frames()`,
`close()`). Bundled:

- `MicrophoneSource` — live capture via `sounddevice` (16 kHz mono int16).
- `FileSource` — decodes any ffmpeg-readable file (wav/m4a/mp3/…) via
  faster-whisper's bundled `decode_audio`, yielded as fast as decode allows.

Implement your own (e.g. a WebSocket source) by satisfying the protocol.

## Voice activity detection (`harp.vad`)

`SpeechDetector` is a `Protocol` returning `(start, end)` sample spans.

- `SileroDetector` wraps the Silero VAD bundled with faster-whisper.
- `NullDetector` reports no speech; the engine then force-cuts at
  `max_segment`. Used when VAD is disabled or fails to load.

## Transcription engine (`harp.whisper.LocalWhisperEngine`)

A wrapper around `faster-whisper` that keeps the model resident. `beam_size` is
configurable (default 5; streaming uses 1). Includes a fail-soft fallback: a
CUDA / compute-type failure on first inference re-initializes on CPU. The CLI
promotes `compute_type=default`→`int8` on CPU (~2× over float32).

## Output (`harp.input.WaylandTyper`, clipboard)

`harp start` delivers the session's final text into the focused window via a
single clipboard paste (`Ctrl+V`); `harp transcribe` prints to the terminal and
can append to a file (`-o`). `WaylandTyper` supports safe mode (alphanumerics
only) and full mode (all symbols, with Unicode hex-sequence emulation).

---

*Next: See [Development Guide](develop.md) to learn how to contribute, or
[Harp as a library](library.md) to drive the engine from your own code.*
