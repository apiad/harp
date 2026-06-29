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
- `src/harp/events.py` — `TranscriptEvent(committed, transient, is_final, ts)`.
- `src/harp/vad.py` — `SpeechDetector` protocol; `SileroDetector`, `NullDetector`.
- `src/harp/audio.py` — `AudioSource` protocol; `MicrophoneSource`, `FileSource`.
- `src/harp/whisper.py` — `LocalWhisperEngine` (faster-whisper wrapper).
- `src/harp/cli/` — `main.py` (commands + `_build_engine`/`_build_detector`),
  `display.py`, `hotkey.py`, `clipboard.py`.

Design + rationale: `docs/design.md`. Public API: `docs/library.md`. Specs and
plans live under `docs/superpowers/`.

## Conventions

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
