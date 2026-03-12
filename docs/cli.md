# CLI Reference

The `harp` command is the main entry point for starting the daemon and managing its configuration and models. Running `harp` without any arguments is equivalent to running `harp start`.

## `harp start`
Starts the background daemon listening for hotkeys.

### Options
| Flag | Description |
| :--- | :--- |
| `-d, --device` | Path or name of the input device (e.g., `/dev/input/event0`). |
| `-t, --toggle` | Use toggle mode (click to start, click to stop) instead of hold mode. |
| `-f, --full` | Type all characters including symbols (opt-in; default is safe mode). |
| `-c, --continuous` | Enable continuous background transcription for long recordings. |
| `-l, --language` | Language code for STT (e.g., `en`, `es`). Default: `auto`. |
| `--local-device` | Hardware device for STT (`cpu`, `cuda`, `auto`). Default: `auto`. |
| `--local-compute-type` | Model quantization (`int8`, `float16`, `float32`, `default`). Default: `default`. |
| `--type / --no-type` | Enable or disable typing results (default is disable). |
| `--copy / --no-copy` | Enable or disable copying results to clipboard (default is disable). |
| `--send-clipboard <num>` | Number of tokens from clipboard to send in Command Mode. |
| `--command-prompt` | Override the default command mode prompt. |

### Hardware Settings Guide
- **`--local-device auto`**: Harp will attempt to use CUDA if an NVIDIA GPU is found, otherwise it defaults to CPU.
- **`--local-compute-type default`**: Automatically selects the fastest supported quantization for your hardware (e.g., `float32` on CPU, `float16` on GPU).
- **`--local-compute-type int8`**: Highly recommended for CPUs with AVX-512 VNNI support for maximum speed.

### Usage Examples
```bash
# Start with defaults (Hold Ctrl+Space to record, print to CLI)
harp

# Explicitly force CPU mode if GPU libraries are missing
harp --local-device cpu

# Toggle mode with full character support and auto-typing
harp start --toggle --full --type

# Only copy to clipboard, don't type
harp start --copy
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
