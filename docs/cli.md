# CLI Reference

The `harp` command is the main entry point for starting the daemon and managing its configuration and models.

## `harp start`
Starts the background daemon listening for hotkeys.

### Options
| Flag | Description |
| :--- | :--- |
| `-d, --device` | Path or name of the input device (e.g., `/dev/input/event0`). |
| `-t, --toggle` | Use toggle mode (click to start, click to stop) instead of hold mode. |
| `-f, --full` | Type all characters including symbols (opt-in; default is safe mode). |
| `--type / --no-type` | Enable or disable typing results (default is enable). |
| `--copy / --no-copy` | Enable or disable copying results to clipboard (default is enable). |
| `--send-clipboard <num>` | Number of tokens from clipboard to send in Command Mode. |
| `--transcribe-prompt` | Override the default transcription prompt. |
| `--command-prompt` | Override the default command mode prompt. |

### Usage Examples
```bash
# Start with defaults (Hold Ctrl+Space to record)
harp start

# Toggle mode with full character support
harp start --toggle --full

# Only copy to clipboard, don't type
harp start --no-type --copy
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
