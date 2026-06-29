# CLI Reference

The `harp` command starts the live-dictation daemon, transcribes files, and
manages configuration and models. Running `harp` with no arguments is
equivalent to `harp start`.

## `harp start`
Starts the hotkey-driven dictation daemon. Hold (or, with `--toggle`, click)
`Ctrl+Space` and speak; on release the session's final text is pasted into the
focused window via a single `Ctrl+V`. Internally it runs the VAD-segmented
streaming engine, so long holds stream chunks as you speak instead of decoding
everything at the end.

### Options
| Flag | Description |
| :--- | :--- |
| `-d, --device` | Path or name of the input device (e.g., `/dev/input/event0`). |
| `-t, --toggle` | Use toggle mode (click to start, click to stop) instead of hold mode. |
| `-f, --full` | Type all characters including symbols (opt-in; default is safe mode). |
| `-l, --language` | Language code for STT (e.g., `en`, `es`). Default: `auto`. |
| `--local-device` | Hardware device for STT (`cpu`, `cuda`, `auto`). Default: `auto`. |
| `--local-compute-type` | Model quantization (`int8`, `float16`, `float32`, `default`). Default: `default` (the CLI promotes `default`→`int8` on CPU). |
| `--paste / --no-paste` | Paste the final transcription into the focused window. Default on. |
| `--slide <seconds>` | Seconds of audio between streaming steps. Default: `1.0`. |

## `harp transcribe <file>`
Stream-transcribe an audio file (any ffmpeg-readable container: wav, m4a, mp3,
…). Finalized text prints in normal weight, the in-progress preview dim.

### Options
| Flag | Description |
| :--- | :--- |
| `-o, --output <file>` | Append finalized text to this file as chunks land (live). |
| `-m, --model <size>` | Whisper model size (tiny, base, small, medium, large-v3). |
| `-l, --language <code>` | Language code. Default: `auto`. |
| `--preview / --no-preview` | Live word-by-word preview of the in-progress chunk. Costs ~2–4× compute; off (default) keeps streaming real-time. |

### Streaming behaviour
The engine finalizes a chunk at each VAD silence boundary (`stream_silence_threshold`),
decoding it once and dropping its audio — finalized speech is never
re-transcribed. In the default finalize-only mode decode work ≈ 1× audio
(measured RTF ≈ 0.34 on `base`/CPU), so it keeps up with real-time. Each chunk
is overlapped by `stream_overlap` seconds (held back and re-decoded with context
to avoid mid-word garbling and seam duplication). Tune `stream_warmup`,
`stream_max_segment`, `stream_overlap`, and `stream_beam_size` in `.harp.yaml`.

**Model choice:** `base` is the recommended floor — robust and real-time on CPU.
`tiny` is faster but can hallucinate sporadically on fluent/pause-less audio;
use it only for latency-critical, error-tolerant cases.

### Hardware Settings Guide
- **`--local-device auto`**: Harp will attempt to use CUDA if an NVIDIA GPU is found, otherwise it defaults to CPU.
- **`--local-compute-type default`**: Automatically selects the fastest supported quantization for your hardware (e.g., `float32` on CPU, `float16` on GPU).
- **`--local-compute-type int8`**: Highly recommended for CPUs with AVX-512 VNNI support for maximum speed.

### Usage Examples
```bash
# Start live dictation (hold Ctrl+Space; final text pasted on release)
harp

# Toggle mode, full symbols (for dictating code/URLs)
harp start --toggle --full

# Transcribe a meeting recording to a file, live
harp transcribe meeting.m4a -m base -l en -o meeting.md

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
