# AGENTS.md — harp

Local-first, real-time speech-to-text **engine** for Linux/Wayland with two
front-ends: live hotkey dictation (`harp start`) and file transcription
(`harp transcribe`). Python 3.12+, `faster-whisper`, `uv`.

## Orientation

The deliverable is the **engine**; the CLI and any external app are just
consumers of its event stream.

- `src/harp/streaming.py` — `StreamingTranscriber`: pure, I/O-free VAD-segmented
  core. Warm-up → finalize-once-and-drop at silence boundaries → force-cut.
  Injected `transcribe` callable + `SpeechDetector`.
- `src/harp/session.py` — `HarpSession`: threads the engine, emits
  `TranscriptEvent`s. Step cadence is **audio-time-driven** (not wall-clock).
- `src/harp/dictation.py` — `DictationSession`: **full / record-then-transcribe**
  mode for bounded push-to-talk. Buffers the whole clip on a worker thread,
  decodes once on `stop()`. The other half of the two-mode model (below).
- `src/harp/events.py` — `TranscriptEvent(committed, transient, is_final, ts)`.
- `src/harp/vad.py` — `SpeechDetector` protocol; `SileroDetector`, `NullDetector`.
- `src/harp/audio.py` — `AudioSource` protocol; `MicrophoneSource`, `FileSource`.
- `src/harp/whisper.py` — `LocalWhisperEngine` (faster-whisper wrapper).
- `src/harp/cli/` — `main.py` (commands + `_build_engine`/`_build_detector`),
  `display.py`, `hotkey.py`, `clipboard.py`.

**Two library modes** (pick by *bounded vs unbounded* audio):

- **`DictationSession`** — full / record-then-transcribe. Bounded push-to-talk
  utterances. One decode of the whole clip on `stop()`; higher quality, no
  seams, no tail-drop. For an **already-complete** blob (server record-then-
  upload) it works over `FileSource`; the threaded buffering adds nothing there,
  so a leaner consumer may just drain the source and decode once.
- **`HarpSession`** — incremental / streaming. Unbounded long-form (meetings, a
  long upload). Yields `TranscriptEvent`s progressively via `.events()`.

Design + rationale: `docs/design.md`. Public API: `docs/library.md`. Specs and
plans live under `docs/superpowers/`.

## Conventions

- **Packaging:** the base package (`pip install harpio`) is the **streaming
  engine only** — `faster-whisper` + `numpy`, no Wayland/desktop deps. The
  dictation daemon (`harp start`) needs `harpio[cli]` (the `cli` extra:
  `evdev`/`pynput`/`python-uinput`/`sounddevice`/`typer`/…). Servers that embed
  the engine (e.g. warden) depend on the base package. `import harp` must stay
  free of `sounddevice` at module load — it's lazily imported in
  `MicrophoneSource.frames()` (patchable as `harp.audio.sd`). The makefile runs
  tests with `--extra cli` so the daemon tests still cover.
- **Commit straight to `main`** (no PR unless asked). Conventional commits.
- **TDD.** Every change starts with a failing test. Tests run inline, never
  delegated. `make test` (fast) / `make test-integration` (real models, slow).
- **Lint as its own step:** `uv run ruff check src tests` — never pipe the gate.
- The engine stays pure: it must remain testable with fakes, no model load.
- Default streaming is **finalize-only** (real-time). The transient preview is
  opt-in (`--preview` / `stream_transient`) because re-decoding the in-progress
  chunk costs ~2–4× and blocks real-time on CPU.

## know-how/ — reach for these by task

- `know-how/streaming-engine.md` — *when changing transcription behaviour,
  latency, chunk boundaries, real-time performance, or adding an AudioSource /
  SpeechDetector.* How the engine streams, why it's real-time, and the tuning
  knobs.
