# Harp 🎵

[![Version](https://img.shields.io/badge/version-v0.4.0-blue.svg)](https://github.com/apiad/harp/releases/tag/v0.4.0)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/apiad/harp/actions/workflows/ci.yml/badge.svg)](https://github.com/apiad/harp/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

**Harp** is a powerful background daemon for Linux (specifically Wayland) that turns your voice into text, typed directly into any active window. Harp is now **local-first**, using `faster-whisper` for high-performance, private, and near-instant transcription. It can also be integrated with **any OpenAI-compatible LLM provider** for intelligent command processing and post-processing.

## 📚 Documentation

For in-depth information, please refer to our documentation:

- [**CLI Reference**](docs/cli.md): Full guide to the `harp` command and its options.
- [**Deployment & Setup**](docs/deploy.md): Detailed guide on permissions, dependencies, and configuration.
- [**Internal Architecture**](docs/design.md): How Harp works under the hood.
- [**Development Guide**](docs/develop.md): How to contribute and run tests.

## ✨ Features
...
- **Local-First Transcription**: Powered by `faster-whisper`, ensuring your voice data stays on your machine and transcription is lightning-fast.
- **Continuous Processing (Opt-in)**: With `--continuous`, Harp transcribes long recordings incrementally in the background, showing you live feedback in the terminal.
- **Global Hotkey (`Ctrl + Space`)**: Instantly start and stop voice capture from anywhere.
- **Direct Keyboard Emulation**: Transcribed text is typed automatically into your active application.
- **Model Management CLI**: Easily download, list, and manage Whisper models (tiny, base, small, medium, large-v3) directly from the `harp` command.
- **Multimodal Modes**:
    - **Transcription Mode**: Standard "Voice-to-Text" for typing emails, notes, or code.
    - **Command Mode (`Ctrl + Shift + Space`)**: Send locally transcribed text to an LLM (e.g., "Summarize the previous paragraph") and get the response typed back.
- **Flexible Operation**:
    - **Hold Mode**: Record while you hold the hotkey.
    - **Toggle Mode (`--toggle`)**: Click once to start, click again to stop.
- **Clipboard Integration**:
    - **Context Awareness**: In Command Mode, Harp can read your clipboard and send a configurable amount of text to the LLM to provide context.
    - **Auto-Copy**: Automatically copy the final result directly to your clipboard.
- **Modern CLI**: Beautiful terminal interface with colors, spinners, and panels powered by `Rich`.

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

3.  **API Configuration (Optional)**: If you want to use Command Mode, Harp requires an OpenAI-compatible API key. Create a `.env` file in your home or project directory:

```toml
HARP_LLM_API_KEY=your_api_key_here

# Optional: Override the default provider (OpenRouter)
HARP_LLM_BASE_URL=https://openrouter.ai/api/v1
HARP_LLM_MODEL=google/gemini-2.0-flash
```

4.  **Dependencies**: Ensure `libportaudio2` and `wl-clipboard` (for Wayland clipboard support) are installed.

```bash
sudo apt install libportaudio2 wl-clipboard
```

## ⌨️ Usage

Start the daemon using the CLI. By default, it runs in "Hold Mode" and only types safe characters.

```bash
harp start
```

### Configuration & CLI Options

You can customize Harp's behavior using the following flags:

| Option            | Short | Description                                                                         | Use Case                                                                                                                |
| :---------------- | :---- | :---------------------------------------------------------------------------------- | :---------------------------------------------------------------------------------------------------------------------- |
| `--device <path>` | `-d`  | Target a specific input device (e.g., `/dev/input/event0`).                         | Useful if you have multiple keyboards and only want to trigger Harp from one specific device.                           |
| `--toggle`        | `-t`  | Enable toggle mode instead of hold mode.                                            | Press `Ctrl+Space` once to start recording, then press it again to stop and transcribe.                               |
| `--full`          | `-f`  | Disable safe filtering and type all returned characters, including symbols.         | Essential when dictating code, complex punctuation, or URLs.                                                            |
| `--copy`          |       | Automatically copy the final transcribed text to your clipboard.                    | Dictate an idea, let Harp type it out, and also have it ready in your clipboard to paste elsewhere.                    |
| `--send-clipboard`|       | **Command Mode Only:** Send a number of tokens from the clipboard as context to LLM. | Copy an email, press `Ctrl+Shift+Space`, and say "Draft a polite decline to this email."                                |
| `--type`          |       | Enable typing the result (default: False).                                          | Enable with `harp start --type` to type directly into active windows.                 |

### Examples

**Programmer Mode:** Toggle recording, type all code symbols, and copy the result to clipboard.
```bash
harp start --toggle --full --copy
```

**Contextual Assistant:** Use clipboard context and limit to the last 1000 tokens.
```bash
harp start --send-clipboard 1000
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
