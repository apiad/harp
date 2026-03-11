# Implementation Plan: Local-First Whisper Refactor

This plan details the transition of 'harp' to a local-first architecture using `faster-whisper`, featuring concurrent background transcription and a new model management CLI.

## Objective
Refactor the transcription pipeline to prioritize local execution and minimize latency.
- **Remove VAD:** Rely strictly on manual start/stop signals (`ctrl+space`).
- **Concurrent Transcription:** Transcribe the audio buffer in a background task while recording is in progress.
- **Model Management CLI:** Add tools to manage `faster-whisper` models locally.
- **Text-Only LLM:** Update the API integration to use local transcription text for Command Mode.

## Architectural Impact
- **Pipeline:** `Microphone -> AudioStreamer -> [Background LocalWhisperEngine] -> HarpDaemon -> Output/LLM`.
- **Latency:** Results are processed incrementally during recording, making the final transcription available almost instantly after stopping.
- **Privacy:** Voice data no longer leaves the local machine; only transcribed text is sent to the LLM (if Command Mode is enabled).

## File Operations

### New Files
- `src/harp/whisper.py`: Contains `LocalWhisperEngine` class for interfacing with `faster-whisper`.

### Modified Files
- `pyproject.toml`: Add `faster-whisper` to dependencies.
- `src/harp/config.py`: Add settings for `whisper_model`, `whisper_device`, and `whisper_compute_type`.
- `src/harp/api.py`: Refactor `OpenRouterClient` into a text-only `LLMClient`.
- `src/harp/daemon.py`: Integrate background transcription task and refactor recording lifecycle.
- `src/harp/__main__.py`: Add the `models` command group.

## Step-by-Step Execution

### Step 1: Dependency Management
- Add `faster-whisper` to `pyproject.toml`.
- Ensure `ctranslate2` and `tokenizers` are included.

### Step 2: Implement Local Whisper Engine
- Create `src/harp/whisper.py`.
- Implement `LocalWhisperEngine.transcribe(audio_data: np.ndarray) -> str`.
- Use `faster_whisper.WhisperModel` with configurable device (`cpu`, `cuda`) and compute type.
- Implement model download/listing logic.

### Step 3: Update Configuration
- Add `whisper_model` (default: "base"), `whisper_device` (default: "auto"), and `whisper_compute_type` (default: "int8") to `HarpConfig`.

### Step 4: Refactor LLM Client
- Update `src/harp/api.py`.
- Change the `transcribe` method to `process_text(text: str, instruction: str)`.
- Use standard Chat Completions without audio payloads.

### Step 5: Implement Concurrent Transcription in `HarpDaemon`
- **Background Task**: Launch `_background_transcription_loop` when recording starts.
- **Incremental Processing**: Every ~0.5s, the loop should:
    1. Grab the current full buffer from `AudioStreamer`.
    2. Run transcription in an executor thread.
    3. Update a `self._latest_transcription` cache.
- **Final Flush**: In `_stop_recording`, cancel the loop and perform one final high-accuracy transcription of the full buffer.

### Step 6: Model Management CLI
- Add `models` command group to `src/harp/__main__.py`.
- Commands: `list`, `download [model_name]`, `remove [model_name]`.

## Testing Strategy
- **Unit Tests**: Test `LocalWhisperEngine` with various audio samples.
- **Latency Benchmarking**: Measure the time from "stop recording" to "text typed" (Target: <300ms).
- **Integration Tests**: Verify that `ctrl+shift+space` (Command Mode) correctly sends the *locally* transcribed text to the cloud LLM.
