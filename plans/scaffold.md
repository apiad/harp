# Harpo Project Scaffolding Plan

This plan outlines the steps to initialize the `Harp` background daemon project using `uv` for Python 3.12, `Ruff` for linting, and `pytest` for testing, following a `src/` layout.

## Phase 1: Initialization
- [ ] Initialize the project structure using `uv init --lib`.
- [ ] Configure `pyproject.toml` for Python 3.12 and the `src/` layout.
- [ ] Set up the directory structure:
  - `src/harp/`
  - `tests/`

## Phase 2: Dependency Management
- [ ] Add runtime dependencies:
  - `openai` (OpenRouter client)
  - `sounddevice` (Audio capture)
  - `python-uinput` (Keyboard emulation)
  - `typer` (CLI interface)
  - `pydantic-settings` (Configuration)
  - `numpy` (Audio processing)
- [ ] Add development dependencies:
  - `ruff` (Linting and formatting)
  - `pytest` (Testing)
  - `pytest-asyncio` (Async testing support)

## Phase 3: File Scaffolding
- [ ] Create core module files with basic structure and typing:
  - `src/harp/__init__.py`
  - `src/harp/__main__.py` (Typer entry point)
  - `src/harp/daemon.py` (Main loop and state management)
  - `src/harp/audio.py` (Audio streamer)
  - `src/harp/api.py` (OpenRouter API client)
  - `src/harp/input.py` (uinput keyboard device)
  - `src/harp/config.py` (Pydantic settings)
- [ ] Create a basic test file `tests/test_daemon.py`.

## Phase 4: Automation and Validation
- [ ] Create a `makefile` in the root directory with the following targets:
  - `lint`: Run `ruff check .` and `ruff format --check .`
  - `test`: Run `pytest`
  - `format`: Run `ruff format .`
  - `check`: Run `lint` and `test` (Default target)
- [ ] Execute `make` to verify the setup.

## Technical Details
- **AsyncIO:** The `daemon.py` will implement an `asyncio` loop for non-blocking API calls.
- **Wayland/uinput:** The `WaylandTyper` will require appropriate permissions (usually `uinput` group).
- **Global Shortcuts:** `pydbus` will be used for a placeholder implementation.
