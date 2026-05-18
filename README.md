# Harp 🎵

[![Version](https://img.shields.io/badge/version-v0.6.0-blue.svg)](https://github.com/apiad/harp/releases/tag/v0.6.0)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/apiad/harp/actions/workflows/ci.yml/badge.svg)](https://github.com/apiad/harp/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

**Harp** is a background daemon for Linux (Wayland) that turns your voice into text, typed live into the focused window. Harp is **local-first and real-time**: while you hold (or, in toggle mode, after you click) `Ctrl+Space`, audio is re-decoded over a rolling window with `faster-whisper`, and the stable prefix is typed as you speak — with minimal backspace+retype back-patches when the model revises an earlier word. There is no cloud LLM step and no separate command mode: one hotkey, one mode, fully on-device.

## 📚 Documentation

For in-depth information, please refer to our documentation:

- [**CLI Reference**](docs/cli.md): Full guide to the `harp` command and its options.
- [**Deployment & Setup**](docs/deploy.md): Detailed guide on permissions, dependencies, and configuration.
- [**Internal Architecture**](docs/design.md): How Harp works under the hood.
- [**Development Guide**](docs/develop.md): How to contribute and run tests.

## ✨ Features
...
- **Local-First, Fully Offline**: Powered by `faster-whisper`. Your voice never leaves your machine.
- **Real-Time Streaming Dictation**: While you speak, Harp re-decodes a rolling window and types the stable prefix live, using LocalAgreement-2 to commit only words confirmed across consecutive passes.
- **Back-Patch Typing**: When the model revises an earlier word, Harp emits a minimal `backspace + retype` diff instead of waiting until the end — your buffer always reflects the current best transcription.
- **Single Hotkey, Single Mode (`Ctrl + Space`)**: Hold to dictate, or `--toggle` to click-on / click-off. No separate command mode; no clipboard-context mode.
- **Direct Keyboard Emulation**: Transcribed text is typed directly into the focused application via `uinput`.
- **Model Management CLI**: Easily download, list, and manage Whisper models (tiny, base, small, medium, large-v3) via `harp models`.
- **Tunable Cadence (`--slide`)**: Control how often the rolling window is re-decoded — match it to your hardware's decode wall-time for stable streaming.
- **Modern CLI**: Terminal UI powered by `Rich`.

## 🚀 Installation

### Using `uv` (Recommended)

The fastest way to run Harp without manual environment setup:

```bash
uvx harpio
```

### Using `pipx`

For a persistent global installation:

```bash
pipx install harpio
```

### From Source

```bash
git clone https://github.com/apiad/harp.git
cd harp
uv sync
uv run harp start
```

## 🛠 Setup & Requirements

1.  **Permissions**: Harp requires access to `/dev/input` and `/dev/uinput`.

```bash
sudo usermod -aG input $USER
# You may also need to set udev rules for uinput or run:
sudo chmod 666 /dev/uinput
```

2.  **Whisper Model**: Before starting for the first time, download a Whisper model.

```bash
harp models download base
```

3.  **Dependencies**: Ensure `libportaudio2` and `wl-clipboard` (for Wayland clipboard support) are installed.

```bash
sudo apt install libportaudio2 wl-clipboard
```

## ⌨️ Usage

Start the daemon using the CLI. By default, running `harp` without arguments starts the background daemon in "Hold Mode" and only prints the result to the terminal.

```bash
harp
```

### Commands

- `harp`: Starts the background daemon (alias for `harp start`).
- `harp start`: Starts the background daemon with explicit options.

### Configuration & CLI Options

You can customize Harp's behavior using the following flags:

| Option            | Short | Description                                                                         | Use Case                                                                                                                |
| :---------------- | :---- | :---------------------------------------------------------------------------------- | :---------------------------------------------------------------------------------------------------------------------- |
| `--device <path>` | `-d`  | Target a specific input device (e.g., `/dev/input/event0`).                         | Useful if you have multiple keyboards and only want to trigger Harp from one specific device.                           |
| `--toggle`        | `-t`  | Enable toggle mode instead of hold mode.                                            | Press `Ctrl+Space` once to start dictating, press again to finalize.                                                    |
| `--full`          | `-f`  | Disable safe filtering and type all returned characters, including symbols.         | Essential when dictating code, complex punctuation, or URLs.                                                            |
| `--copy`          |       | Automatically copy the final transcribed text to your clipboard.                    | Dictate an idea, let Harp type it live, and also have the final text ready to paste elsewhere.                          |
| `--type`          |       | Type the streaming result live into the focused window (default: False).            | Enable with `harp start --type` to use Harp as a real-time dictation engine.                                            |
| `--slide <s>`     |       | Cadence between rolling re-decode passes (seconds). Default: `1.0`.                 | Raise on slower CPUs / larger models so the slide stays above single-window decode time.                                |

### Examples

**Live dictation, all symbols, toggle:**
```bash
harp start --toggle --full --type
```

**Slow CPU with a larger model:** raise the slide so re-decodes don't queue.
```bash
harp start --type --slide 1.5
```

## 🤝 Contributing

Contributions are what make the open-source community such an amazing place to learn, inspire, and create. Any contributions you make are **greatly appreciated**.

### 🤖 Gemini CLI

This repository is enhanced with custom **Gemini CLI** commands to automate common tasks and workflows. If you are using Gemini, you can run:

```bash
gemini /onboard
```
to get started, explore the project architecture, and understand the automated workflows (planning, debugging, releases, etc.).

### Standard Process

1.  **Report Bugs**: Open an [issue](https://github.com/apiad/harp/issues) if you find something broken.
2.  **Suggest Features**: Have an idea for a new mode? Let us know!
3.  **Submit Pull Requests**:
    - Fork the project.
    - Create your Feature Branch (`git checkout -b feature/AmazingFeature`).
    - Commit your changes (`git commit -m 'feat: Add some AmazingFeature'`).
    - Push to the branch (`git push origin feature/AmazingFeature`).
    - Open a Pull Request.

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.
