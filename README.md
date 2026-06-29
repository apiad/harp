# Harp 🎵

[![Version](https://img.shields.io/badge/version-v0.8.1-blue.svg)](https://github.com/apiad/harp/releases/tag/v0.8.1)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/apiad/harp/actions/workflows/ci.yml/badge.svg)](https://github.com/apiad/harp/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

**Harp** is a local-first, real-time speech-to-text **engine** for Linux
(Wayland) with two front-ends:

- **Live dictation** (`harp start`) — hold (or toggle) `Ctrl+Space` and speak;
  the final transcription is pasted into the focused window on release.
- **File transcription** (`harp transcribe <file>`) — stream-transcribe a
  recording (meeting, lecture, voice memo) in near real-time, printed live and
  optionally appended to a file.

Under the hood a **VAD-segmented streaming engine** finalizes each spoken chunk
at silence boundaries (via Silero VAD), decoding it **once** with
`faster-whisper` and never re-transcribing finalized speech — so a long
recording streams out as you go instead of waiting for the end. Everything is
on-device; there is no cloud step.

## 📚 Documentation

For in-depth information, please refer to our documentation:

- [**CLI Reference**](docs/cli.md): Full guide to the `harp` command and its options.
- [**Deployment & Setup**](docs/deploy.md): Detailed guide on permissions, dependencies, and configuration.
- [**Internal Architecture**](docs/design.md): How Harp works under the hood.
- [**Development Guide**](docs/develop.md): How to contribute and run tests.

## ✨ Features

- **Local-First, Fully Offline**: Powered by `faster-whisper`. Your voice never leaves your machine.
- **VAD-Segmented Streaming Engine**: Finalizes each spoken chunk at silence boundaries (Silero VAD), decoding it **once** and never re-transcribing finalized speech — so long audio streams out as you go. Real-time on CPU (RTF ≈ 0.34 on `base`).
- **Long-Form File Transcription** (`harp transcribe`): Stream-transcribe meetings, lectures, and voice memos in near real-time; print live and append to a file with `-o`.
- **Live Dictation** (`harp start`): Hold (or `--toggle`) `Ctrl + Space`; the final transcription is pasted into the focused window via `uinput` on release.
- **Library-First**: Drive a `HarpSession` from your own code; it emits two-tier `TranscriptEvent`s (committed + transient). See [`docs/library.md`](docs/library.md).
- **Model Management CLI**: Download, list, and manage Whisper models (tiny, base, small, medium, large-v3) via `harp models`.
- **Modern CLI**: Terminal UI powered by `Rich`.

> **Model choice:** `base` is the recommended floor — robust and real-time on CPU. `tiny` is faster but can hallucinate on fluent/pause-less audio; use it only for latency-critical, error-tolerant cases.

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

- `harp` / `harp start`: Start the live-dictation daemon (hotkey-driven).
- `harp transcribe <file>`: Stream-transcribe an audio file.
- `harp models <download|list|remove>`: Manage local Whisper models.
- `harp config` / `harp init`: Inspect or scaffold `.harp.yaml`.

### `harp start` options

| Option            | Short | Description                                                                  |
| :---------------- | :---- | :-------------------------------------------------------------------------- |
| `--device <path>` | `-d`  | Target a specific input device (e.g., `/dev/input/event0`).                 |
| `--toggle`        | `-t`  | Toggle mode: press `Ctrl+Space` to start, press again to finalize.          |
| `--full`          | `-f`  | Type all characters including symbols (for code, punctuation, URLs).        |
| `--paste` / `--no-paste` | | Paste (`Ctrl+V`) the final text into the focused window. Default on.   |
| `--slide <s>`     |       | Seconds of audio between streaming steps. Default `1.0`.                     |
| `--language <c>`  | `-l`  | Language code (e.g. `en`, `es`). Default: auto-detect.                       |

### `harp transcribe` options

| Option           | Short | Description                                                          |
| :--------------- | :---- | :----------------------------------------------------------------- |
| `--output <f>`   | `-o`  | Append finalized text to this file as chunks land (live).          |
| `--model <size>` | `-m`  | Whisper model size (tiny, base, small, medium, large-v3).          |
| `--language <c>` | `-l`  | Language code. Default: auto-detect.                               |
| `--preview`      |       | Live word-by-word preview of the in-progress chunk (costs ~2–4× compute; off keeps streaming real-time). |

### Examples

**Transcribe a meeting recording to a file, live:**
```bash
harp transcribe meeting.m4a -m base -l en -o meeting.md
```

**Live dictation, all symbols, toggle mode:**
```bash
harp start --toggle --full
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
