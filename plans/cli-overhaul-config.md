# Plan: CLI & Configuration Overhaul

## Objective
Refactor the `harp` CLI to support hierarchical YAML configuration (`.harp.yaml`), more flexible output modes (`--type`, `--copy`, `--send-clipboard`), and configuration management commands (`--config`, `--init`).

## Key Requirements
1.  **Output Mode Flags:**
    *   `--type`: Type the transcription result.
    *   `--copy`: Copy the transcription result to the clipboard.
    *   `--send-clipboard TOKENS`: (Formerly `--clipboard`) If `TOKENS` > 0, send that many tokens from the *existing* clipboard content to the command mode. If 0, send nothing.
    *   **Always** print the result to the daemon's `stdout` (CLI).
    *   If multiple flags (`--type`, `--copy`, `--send-clipboard`) are provided, perform all requested actions.
    *   Flags apply to both "transcribe" and "command" modes.
2.  **Prompt Flags:**
    *   Update/rename flags for `--command-prompt` and `--transcribe-prompt`.
3.  **Configuration File (`.harp.yaml`):**
    *   Implement configuration loading from `.harp.yaml`.
    *   Search for `.harp.yaml` from the current directory up to the user's home directory.
    *   The nearest `.harp.yaml` file wins.
    *   CLI flags override `.harp.yaml` values.
4.  **New CLI Commands:**
    *   `--config`: Show the currently resolved configuration.
    *   `--init`: Create a default `.harp.yaml` in the current folder (error if it exists).

## Technical Implementation

### 1. Dependencies
- Add `PyYAML` to `pyproject.toml`.

### 2. Configuration (`src/harp/config.py`)
- Define a `Config` Pydantic model.
- Implement `load_config()` to search for `.harp.yaml` up the directory tree to `$HOME`.
- Use "Nearest Wins" logic.

### 3. Daemon (`src/harp/daemon.py`)
- Modify processing logic to:
    1. Always print the result to `stdout`.
    2. If `config.type`, type the result.
    3. If `config.copy`, copy to clipboard.
    4. If `config.send_clipboard > 0`, send tokens from existing clipboard.

### 4. CLI (`src/harp/__main__.py`)
- Update `Typer` app with new flags.
- Implement `--config` and `--init` commands.
- Merge CLI flags with `.harp.yaml` values (CLI wins).

## Step-by-Step Implementation
1. Update `pyproject.toml` with `PyYAML`.
2. Refactor `src/harp/config.py` for hierarchical YAML loading.
3. Update `src/harp/daemon.py` output logic.
4. Update `src/harp/__main__.py` CLI flags and commands.
5. Verify and test.
