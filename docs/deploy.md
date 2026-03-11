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
local_compute_type: "default"

# LLM Settings (for Command Mode)
llm_api_key: "your_key"
llm_base_url: "https://openrouter.ai/api/v1"
llm_model: "google/gemini-2.0-flash"

# Behavior
toggle: false
type: false
copy: false
```

## 🖥️ Hardware & GPU Acceleration

Harp's local transcription engine (`faster-whisper`) is optimized for both CPU and NVIDIA GPU (CUDA) execution.

### The `libcublas` Issue
If you have an NVIDIA GPU but lack the necessary system libraries, you might see an error like:
`RuntimeError: Library libcublas.so.12 is not found or cannot be loaded`

This typically happens if the CUDA Toolkit 12 is not installed or not in your system path.

### Automatic Fallback
Harp is designed to be resilient. If it detects a failure in the GPU/CUDA backend or an unsupported quantization type (like `int8` on older CPUs), it will:
1.  **Catch the error** during the first transcription pass.
2.  **Log a warning** to your terminal.
3.  **Automatically fall back** to `device="cpu"` and `compute_type="default"`.
4.  **Reload the model** and complete your transcription without further intervention.

### Manual CPU Mode
If you wish to avoid GPU detection entirely (e.g., to save VRAM or power), you can force CPU mode in your `.harp.yaml`:
```yaml
local_device: "cpu"
local_compute_type: "default"
```
Or via the CLI:
```bash
harp start --local-device cpu
```

## 🚀 Execution

Always ensure at least one Whisper model is downloaded before running the daemon:
```bash
harp models download base
harp start
```

---

*Next: See [Design & Architecture](design.md) to learn how Harp works.*
