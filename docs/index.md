# Harp 🎵

**Harp** is a local-first, real-time speech-to-text engine for Linux (Wayland),
with a hotkey dictation daemon and a file-transcription command.

## Vision

A seamless, private, near-instantaneous voice-to-text interface. By keeping all
transcription **local-first**, your voice data never leaves your machine.

## Core Concepts

### Local-First STT
Harp uses `faster-whisper` for local Speech-to-Text inference — no cloud audio
processing, better privacy, no network latency.

### VAD-Segmented Streaming
Harp finalizes each spoken chunk at silence boundaries (Silero VAD), decoding it
**once** and never re-transcribing finalized speech. A long recording streams
out as you go instead of waiting for the end, and the result is ready almost the
moment audio stops. The engine is real-time on CPU (RTF ≈ 0.34 on `base`).

### Two Front-Ends
- **Live dictation** (`harp start`): hold/toggle `Ctrl+Space`; the final text is
  pasted into the focused window on release.
- **File transcription** (`harp transcribe <file>`): stream a recording to the
  terminal and, with `-o`, append it to a file live.

## Key Features

- **Global Wayland Hotkeys**: Works across all applications using `evdev` and `uinput`.
- **Keyboard Emulation**: Pastes results into the active window, supporting Unicode and special characters.
- **Model Management**: Simple CLI for downloading and managing Whisper models.
- **Library-First**: Drive a `HarpSession` from your own code (`docs/library.md`).

---

*Next: See [CLI Reference](cli.md) to learn how to use the `harp` command.*
