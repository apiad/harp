# Harp 🎵

**Harp** is a high-performance background daemon for Linux (specifically Wayland) that converts your voice into text, typed directly into any active application.

## Vision

Harp aims to provide a seamless, private, and near-instantaneous voice-to-text interface. By prioritizing **local-first** transcription, Harp ensures that your voice data never leaves your machine while achieving sub-300ms latency from speech to text.

## Core Concepts

### Local-First STT
Harp uses `faster-whisper` for local Speech-to-Text (STT) inference. This eliminates the need for cloud-based audio processing, improving privacy and reducing network latency.

### Concurrent Pipeline
Unlike traditional tools that wait for you to stop speaking before transcribing, Harp transcribes your voice in the background *while* you speak. This "record-and-stream" approach means the final result is ready almost the moment you release the hotkey.

### Modal Operation
Harp operates in two primary modes:
- **Transcription Mode**: Standard voice-to-text for dictating emails, documents, or code.
- **Command Mode**: (Ctrl + Shift + Space) Sends the locally transcribed text to an LLM to execute instructions or process context (e.g., "Summarize this paragraph").

## Key Features

- **Global Wayland Hotkeys**: Works across all applications using `evdev` and `uinput`.
- **Keyboard Emulation**: Types results directly into the active window, supporting Unicode and special characters.
- **Model Management**: Simple CLI for downloading and managing Whisper models.
- **Clipboard Integration**: Context-aware commands using your current clipboard data.

---

*Next: See [CLI Reference](cli.md) to learn how to use the `harp` command.*
