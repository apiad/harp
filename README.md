# Harp 🎵

[![Version](https://img.shields.io/badge/version-v0.2.3-blue.svg)](https://github.com/apiad/harp/releases/tag/v0.2.3)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/apiad/harp/actions/workflows/ci.yml/badge.svg)](https://github.com/apiad/harp/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

**Harp** is a powerful background daemon for Linux (specifically Wayland) that turns your voice into text, typed directly into any active window. It uses OpenRouter's multimodal APIs to provide high-quality transcription and intelligent command processing.

## ✨ Features

- **Global Hotkey (`Ctrl + Space`)**: Instantly start and stop voice capture from anywhere.
- **Direct Keyboard Emulation**: Transcribed text is typed automatically into your active application.
- **Multimodal Modes**:
    - **Transcription Mode**: Standard "Voice-to-Text" for typing emails, notes, or code.
    - **Command Mode (`Ctrl + Shift + Space`)**: Send voice instructions to the LLM (e.g., "Summarize the previous paragraph") and get the response typed back.
- **Flexible Operation**:
    - **Hold Mode**: Record while you hold the hotkey.
    - **Toggle Mode (`--toggle`)**: Click once to start, click again to stop.
- **Clipboard Integration**:
    - **Context Awareness (`--clipboard`)**: In Command Mode, Harp can read your clipboard and send the last 500 words (configurable) to the LLM to provide context (e.g., "Summarize the text I just copied").
    - **Auto-Copy (`--to-clipboard`)**: Automatically copy the final transcribed text or command result directly to your clipboard for easy pasting elsewhere.
- **Robust Typing**:
    - Supports standard US-ASCII and Latin characters (tildes, ñ, etc.).
    - **Safe Filtering**: By default, only types letters and numbers to avoid accidental shortcut triggers. Use `--full` to type everything.
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
2.  **API Key**: Create a `.env` file in your home or project directory:

```env
HARP_API_KEY=your_openrouter_api_key
```
3.  **Dependencies**: Ensure `libportaudio2` and `xclip` or `wl-clipboard` (for `pyperclip` support on Linux) are installed on your system.

```bash
sudo apt install libportaudio2 xclip
```

## ⌨️ Usage

Start the daemon using the CLI. By default, it runs in "Hold Mode" and only types safe characters.

```bash
harp
```

### Configuration & CLI Options

You can customize Harp's behavior using the following flags:

| Option | Short | Description | Use Case |
| :--- | :--- | :--- | :--- |
| `--device <path>` | `-d` | Target a specific input device (e.g., `/dev/input/event0`). | Useful if you have multiple keyboards and only want to trigger Harp from one specific device. |
| `--toggle` | `-t` | Enable toggle mode instead of hold mode. | Press `Ctrl+Space` once to start recording, then press it again to stop and transcribe. |
| `--full` | `-f` | Disable safe filtering and type all returned characters, including symbols. | Essential when dictating code, complex punctuation, or URLs. |
| `--clipboard` | `-c` | **Command Mode Only:** Send the current clipboard content as context to the LLM. | Copy an email, press `Ctrl+Shift+Space`, and say "Draft a polite decline to this email." |
| `--tokens <num>` | `-n` | Set the number of words to include when sending clipboard context. (Default: `500`) | Use `--tokens 1000` to provide larger context documents without blowing up your API costs. |
| `--to-clipboard` | `-C` | Automatically copy the final transcribed text (or command result) to your clipboard. | Dictate an idea, let Harp type it out, and also have it ready in your clipboard to paste into another app immediately. |

### Examples

**Programmer Mode:** Toggle recording, type all code symbols, and copy the result to clipboard.
```bash
harp --toggle --full --to-clipboard
```

**Contextual Assistant:** Use clipboard context and limit to the last 1000 words.
```bash
harp --clipboard --tokens 1000
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
