# Deployment & Execution Guide

Setting up Harp on a Linux system requires a few specific steps to handle input permissions and dependencies.

## 📦 System Dependencies

Harp requires several system-level libraries for audio capture and input emulation:

- `libportaudio2`: For microphone capture (`sounddevice`).
- `wl-clipboard`: For clipboard access on Wayland (`pyperclip`).
- `notify-send`: For desktop status notifications (often part of `libnotify`).

**Debian/Ubuntu/Fedora/Arch:**
```bash
# Debian/Ubuntu
sudo apt install libportaudio2 wl-clipboard libnotify-bin

# Arch
sudo pacman -S portaudio wl-clipboard libnotify
```

## 🔐 Permissions

Harp needs permission to **read** raw keyboard events from `/dev/input` and **write** virtual events to `/dev/uinput`.

### Group Membership
Add your user to the `input` group:
```bash
sudo usermod -aG input $USER
```
*(Logout and log back in for this to take effect.)*

### uinput Rules
You may need to explicitly allow your user to write to `/dev/uinput`. You can do this permanently with a udev rule:
```bash
echo 'KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"' | sudo tee /etc/udev/rules.d/99-uinput.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

## ⚙️ Configuration

Harp can be configured via environment variables (prefixed with `HARP_`) or a `.harp.yaml` file.

### Order of Precedence
1. CLI Arguments (e.g., `--toggle`).
2. Environment Variables (`HARP_TOGGLE=true`).
3. Local `.harp.yaml`.
4. Home directory `~/.harp.yaml`.
5. Default settings.

### Configuration Reference (`.harp.yaml`)
```yaml
# Local STT Settings
local_model: "base"
local_device: "auto"
local_compute_type: "int8"

# LLM Settings (for Command Mode)
llm_api_key: "your_key"
llm_base_url: "https://openrouter.ai/api/v1"
llm_model: "google/gemini-2.0-flash"

# Behavior
toggle: false
type: true
copy: true
```

## 🚀 Execution

Always ensure at least one Whisper model is downloaded before running the daemon:
```bash
harp models download base
harp start
```

---

*Next: See [Design & Architecture](design.md) to learn how Harp works.*
