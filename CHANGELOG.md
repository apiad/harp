# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-03-04

### Added
- **Clipboard Context**: Command Mode now reads the clipboard (`--clipboard`) to send contextual data to the LLM (configurable via `--tokens`).
- **Auto-Copy**: Added an option (`--to-clipboard`) to automatically copy the final transcription or command result to the system clipboard.
- **Audio Feedback**: Added generated audio chimes (high pitch for start, low pitch for stop) when toggling recording.
- **System Notifications**: Added desktop notifications (`notify-send`) when the prompt is sent to the LLM and when transcription is ready.

### Changed
- Increased transcription similarity threshold to 95% in end-to-end integration tests.
- Updated README to explicitly clarify support for any multimodal LLM provider with native audio input, and documented API environment variables.

### Removed
- Removed the experimental interactive mode (and its associated HUD) entirely, shifting focus to a highly stable batch-only architecture.

## [0.2.3] - 2026-03-03

### Added
- Expanded test suite with comprehensive unit and integration tests, increasing overall coverage to **75%**.
- New test modules for API, audio, input, CLI entry point, and asynchronous daemon logic.
- Automated coverage reporting using `pytest-cov`.

### Changed
- Refactored `HarpConfig` to use the modern Pydantic `ConfigDict` pattern.
- Extracted keyboard detection logic into a testable static method in `HarpDaemon`.
- Simplified package initialization in `src/harp/__init__.py`.

## [0.2.2] - 2026-03-03

### Changed
- Renamed PyPI distribution package to `harpio` to resolve naming conflicts.
- Refined README.md formatting and improved command usage examples.

## [0.2.1] - 2026-03-03

### Changed
- Updated README.md with comprehensive installation, usage, and Gemini CLI guides.
- Allowed forward slash (`/`) and parentheses (`()`) in the default safe-mode punctuation filtering.
- Synchronized `TASKS.md` with GitHub issues for better roadmap tracking.

### Fixed
- GitHub Actions workflows: Added `libportaudio2` system dependency to fix CI/CD test failures.

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
