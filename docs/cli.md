# CLI Reference

The `harp` command is the main entry point for starting the daemon and managing its configuration and models. Running `harp` without any arguments is equivalent to running `harp start`.

## `harp start`
Starts the background daemon listening for hotkeys. Harp now runs a single **real-time streaming dictation** mode: while you hold (or, with `--toggle`, after you click) `Ctrl+Space`, audio is re-decoded over a rolling window using LocalAgreement-2, and the stable prefix is typed live with minimal backspace+retype back-patches as the model revises.

### Options
| Flag | Description |
| :--- | :--- |
| `-d, --device` | Path or name of the input device (e.g., `/dev/input/event0`). |
| `-t, --toggle` | Use toggle mode (click to start, click to stop) instead of hold mode. |
| `-f, --full` | Type all characters including symbols (opt-in; default is safe mode). |
| `-l, --language` | Language code for STT (e.g., `en`, `es`). Default: `auto`. |
| `--local-device` | Hardware device for STT (`cpu`, `cuda`, `auto`). Default: `auto`. |
| `--local-compute-type` | Model quantization (`int8`, `float16`, `float32`, `default`). Default: `default`. |
| `--type / --no-type` | Enable or disable typing results (default is disable). |
| `--copy / --no-copy` | Enable or disable copying results to clipboard (default is disable). |
| `--slide <seconds>` | Cadence between streaming re-decode passes. Default: `1.0`. Tune up if your decode wall-time exceeds the slide (see below). |

### Streaming cadence (`--slide`)
The streaming loop re-decodes the rolling window every `stream_slide_interval` seconds. For stability, the slide must comfortably exceed the single-window decode time on your machine — rule of thumb: `slide ≥ 1.3 × decode`. The shipped default (`1.0s`) is a placeholder; **live cadence tuning on a mic-equipped host is a pending follow-up**. If you observe queuing or stuttering with `medium`/`large-v3` on CPU, raise `--slide` (or set `stream_slide_interval` in `.harp.yaml`).

### Hardware Settings Guide
- **`--local-device auto`**: Harp will attempt to use CUDA if an NVIDIA GPU is found, otherwise it defaults to CPU.
- **`--local-compute-type default`**: Automatically selects the fastest supported quantization for your hardware (e.g., `float32` on CPU, `float16` on GPU).
- **`--local-compute-type int8`**: Highly recommended for CPUs with AVX-512 VNNI support for maximum speed.

### Usage Examples
```bash
# Start with defaults (Hold Ctrl+Space to dictate live; print to CLI)
harp

# Type live into the focused window, toggle mode, full symbols
harp start --toggle --full --type

# Raise the re-decode cadence to 1.5s on slower CPUs
harp start --slide 1.5

# Force CPU mode if GPU libraries are missing
harp --local-device cpu
```

## `harp models`
Command group for managing local Whisper models.

### `harp models download [size]`
Downloads a model (e.g., `tiny`, `base`, `small`, `medium`, `large-v3`).
*Default size: `base`*

### `harp models list`
Lists all Whisper models currently cached in `~/.cache/harp/models`.

### `harp models remove [name]`
Deletes a specific model from the local cache to free disk space.

## `harp config`
Displays the currently resolved configuration, showing how environment variables, `.harp.yaml`, and CLI flags were merged.

## `harp init`
Creates a default `.harp.yaml` file in the current directory if one does not exist.

---

*Next: See [Deployment & Execution](deploy.md) to set up permissions and dependencies.*
