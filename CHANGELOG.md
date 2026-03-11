# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0] - 2026-03-11

### Added
- **Local-First Transcription**: Integrated `faster-whisper` for high-performance, private, and offline-capable transcription.
- **Concurrent Background Processing**: Implemented an opt-in background transcription loop (`--continuous`) that processes audio *while* the user is speaking, reducing perceived latency to near-zero.
- **Model Management CLI**: New `harp models` command group to `download`, `list`, and `remove` Whisper models (tiny, base, small, medium, large-v3).
- **Text-Only LLM Integration**: Refactored the API client to support any OpenAI-compatible endpoint for Command Mode and post-processing, sending locally transcribed text instead of raw audio.
- **Pre-flight Checks**: Harp now verifies that the configured Whisper model is downloaded before starting the daemon.
- **Hardware Settings**: New flags `--local-device` and `--local-compute-type` to customize STT execution.

### Changed
- **Configuration Refactor**: Updated `HarpConfig` with explicit sections for local STT settings and LLM settings.
- **Dependency Management**: Switched to `faster-whisper` and `huggingface-hub` for model handling.
- **API Client**: Renamed `OpenRouterClient` to `LLMClient` and removed all audio-encoding logic.
- **Optimized CLI**: Moved heavy imports inside commands to make `harp --help`, `harp init`, and `harp config` significantly faster.
- **Safety-First Defaults**: Output modes (`--type` and `--copy`) are now **False** by default to prevent accidental input injection.

### Fixed
- **CUDA Robustness**: Added a graceful fallback to CPU mode if CUDA libraries (like `libcublas`) are missing or if hardware acceleration fails.
- **Model Organization**: Refined model storage to use subdirectories, preventing file conflicts and ensuring accurate listing.
- Updated all unit and integration tests to support the new local-first architecture and mocked AI components for CI stability.

## [0.4.0] - 2026-03-11

### Added
- **Hierarchical Configuration**: Introduced `.harp.yaml` support with "Nearest Wins" search logic (searches from current directory up to `$HOME`).
- **New CLI Commands**: Added `harp config` to view resolved settings and `harp init` to scaffold a default configuration file.
- **Flexible Output Modes**: Added explicit flags for `--type`, `--copy`, and `--send-clipboard` (formerly `--clipboard`).
- **Always-on CLI Output**: Transcription results are now consistently printed to the terminal regardless of other output flags.
- **Research & Planning**: Added comprehensive research on fast transcription optimization and detailed implementation plans for the CLI overhaul.

### Changed
- **Renamed Core Classes**: Standardized naming to `HarpDaemon` and `HarpConfig` across the entire codebase and test suite for consistency.
- **CLI Refactor**: Migrated the main entry point to a subcommand-based structure (`harp start`, `harp config`, `harp init`).
- **Dependency Update**: Added `PyYAML` for configuration parsing.

### Fixed
- Updated all unit and integration tests to align with the new configuration model and class naming conventions.
- Fixed linting and formatting issues in the core configuration and daemon logic.

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
