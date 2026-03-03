# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-03-03

### Added
- Global hotkey listener using `evdev`.
- `uinput` interceptor to suppress hotkeys from reaching active windows.
- Non-blocking audio capture at 16kHz Mono.
- Batch audio transcription via OpenRouter (Base64 audio input).
- `WaylandTyper` for emulating physical keyboard input with Unicode support.
- "Command" mode (`Ctrl + Shift + Space`) for direct voice instructions to LLM.
- CLI options: `--toggle` for state switching and `--full` for opt-in symbol typing.
- Beautified CLI using `Rich` with spinners, colors, and transcription panels.
- GitHub Actions workflows for automated CI (tests/lint matrix) and CD (PyPI).
- Experimental Interactive Mode for real-time transcription (currently marked as broken).

### Changed
- Refined device discovery to target only physical keyboard devices.
- Improved typing robustness with explicit modifier release and tactical delays.

### Fixed
- Terminal pollution (`^@`) when pressing `Ctrl + Space`.
- API `405 Method Not Allowed` errors by switching to multimodal completion format.

## [0.1.0] - 2026-03-03

### Added
- Core daemon structure and placeholders (`src/harp/`).
- Initial daemon state test.
- Scaffolding plan and initial journal entry.

### Changed
- Initialized project with `uv` and dependencies.
- Configured makefile for linting and testing.
- Renamed project and package to `harp`.
