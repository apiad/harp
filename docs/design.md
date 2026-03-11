# Internal Architecture

Harp is built on a modular, concurrent architecture designed to minimize latency and ensure privacy.

## Overview

The daemon sits between your physical keyboard (`evdev`) and a virtual input device (`uinput`). It captures audio while managing a background transcription loop to provide results almost instantly.

## The Pipeline

1. **Input Catching (`HarpDaemon` + `evdev`)**: 
   Harp grabs the physical keyboard device(s) and creates a virtual `uinput` passthrough. All keys are passed through unless the hotkey (`Ctrl + Space`) is detected.
2. **Audio Streaming (`AudioStreamer`)**: 
   While the hotkey is active, raw PCM audio is captured at 16kHz Mono using `sounddevice`.
3. **Background Transcription (`LocalWhisperEngine`)**: 
   A background task (`_background_transcription_loop`) periodically grabs the current audio buffer every 0.5s and performs a speculative transcription.
4. **Final Flush**: 
   Upon release of the hotkey, one final high-accuracy transcription of the full audio buffer is performed.
5. **Command Mode (Optional)**: 
   If `Ctrl + Shift + Space` was used, the transcribed text is sent to an LLM provider (`LLMClient`) with optional clipboard context.
6. **Typing Output (`WaylandTyper`)**: 
   The final string is injected back into the OS as physical keyboard events via `uinput`.

## Key Components

### `HarpDaemon`
The central coordinator. It manages the state machine:
- `IDLE`: Listening for hotkeys and passing through regular typing.
- `RECORDING`: Capturing audio and running the background transcription.
- `PROCESSING`: Finalizing the transcription and handling LLM calls or typing output.

### `LocalWhisperEngine`
A high-performance wrapper around `faster-whisper`. It keeps the selected AI model (e.g., `base`) resident in memory to avoid load-time latency during recording.

**Resiliency**: The engine includes a "fail-soft" mechanism. If a hardware backend (like CUDA) fails due to missing system libraries or incompatible hardware during the first inference pass, the engine automatically catches the error, logs a warning, and re-initializes itself on the CPU.

### `WaylandTyper`
Handles the complexity of typing characters on Linux/Wayland. It supports:
- **Safe Mode**: Only types alphanumeric characters to avoid accidental shortcut triggers.
- **Full Mode**: Types all symbols and special characters.
- **Unicode Support**: Injects characters not present in the current keymap using hex sequence emulation.

---

*Next: See [Development Guide](develop.md) to learn how to contribute.*
