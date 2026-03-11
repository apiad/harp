# Architectural Impact & Roadmap for Local-First Whisper Streaming

This report outlines the technical refactoring, configuration changes, feature impacts, and testing strategies required to transition the `harp` project from batch-based API transcription to local-first continuous streaming using Whisper (specifically `faster-whisper`).

## 1. Required Refactorings for `HarpDaemon`

The current `HarpDaemon` architecture likely follows a sequential state machine: `IDLE` -> `RECORDING` -> `WAITING_FOR_API` -> `TYPING`. To support streaming, the daemon must transition to a concurrent, event-driven model.

### 1.1 Transition to a Continuous Streaming Loop
-   **Audio Capture Thread/Task:** Instead of starting and stopping recording, `HarpDaemon` should maintain a background audio capture process (e.g., using `PyAudio` or `sounddevice`) that pushes raw PCM chunks into a synchronized `Queue`.
-   **Transcription Loop:** A dedicated consumer thread will pull audio chunks from the queue and feed them into the `faster-whisper` engine.
-   **VAD Integration:** Voice Activity Detection (VAD) must be active at all times. The daemon should only process and "finalize" segments when speech is detected. `faster-whisper` has built-in Silero VAD support which can be used to filter out noise and silence efficiently.
-   **Incremental Feedback:** As segments are finalized (or as partial segments are generated), the daemon should emit "TranscriptionEvents" to the UI or the keyboard emulator (`input.py`).

### 1.2 Concurrency Model
-   **Asyncio vs Threads:** Since Whisper inference is CPU/GPU intensive and audio capture is I/O intensive, a hybrid approach is recommended. Use `asyncio` for the main daemon loop and events, but run the Whisper inference in a `ThreadPoolExecutor` or `ProcessPoolExecutor` to avoid blocking the event loop.
-   **Backpressure Handling:** If transcription lags behind real-time (due to hardware limitations), the daemon must implement a strategy to either drop old audio chunks or signal the user to slow down.

---

## 2. Model Management & `.harp.yaml` Integration

Model management should be seamless and transparent to the user, with reasonable defaults and explicit overrides.

### 2.1 Configuration Schema
The `.harp.yaml` should be extended with a `local_whisper` section:

```yaml
local_whisper:
  enabled: true
  model: "distil-large-v3"   # Options: tiny, small, medium, large-v3, distil-large-v3
  device: "auto"             # Options: cpu, cuda, auto
  compute_type: "int8"       # Options: int8, float16, float32, auto
  model_path: "~/.cache/harp/models"
  vad_filter: true
  min_silence_duration: 500  # ms
```

### 2.2 Lifecycle Management
-   **Lazy Loading:** The model should only be loaded into memory when the daemon starts or when the first transcription is requested.
-   **Automated Download:** On startup, the daemon should check if the configured model exists in `model_path`. If not, it should trigger a download using the `huggingface_hub` or `faster-whisper`'s `download_root` parameter.
-   **Version Tracking:** The configuration should track the model version to ensure compatibility after updates.

---

## 3. Impact on "Clipboard Context"

The "Clipboard Context" feature currently likely provides context to the LLM or Whisper API for better accuracy (e.g., technical terms from a doc).

### 3.1 Incremental Transcription Synergy
-   **Initial Prompt Injection:** In local-first mode, the clipboard content should be fetched at the **start** of a streaming session and passed to Whisper's `initial_prompt` parameter. This is the most effective way to bias the model towards technical terms present in the user's current work context.
-   **Dynamic Context:** If the clipboard changes significantly during a long dictation session, the daemon could theoretically update the `initial_prompt` for the next segment, though this may lead to inconsistency in terminology within a single stream.
-   **Context-Aware Refinement:** If the system uses a secondary LLM (via `api.py`) for punctuation and formatting, the clipboard context should still be sent to that LLM along with the incrementally finalized segments.

### 3.2 Challenges
-   **Race Conditions:** Accessing the clipboard frequently during audio capture might cause slight UI lag on some operating systems (e.g., Linux/X11).
-   **Privacy:** Streaming "always-on" transcription with clipboard context needs clear user indicators (e.g., a tray icon or status change) to avoid accidental leaks of sensitive clipboard data into log files or API calls.

---

## 4. Testing Strategy

Transitioning to local inference shifts the testing burden from "mocking API responses" to "simulating hardware and audio streams".

### 4.1 Mocking Local Inference
-   **Inference Mock:** Use `unittest.mock` to wrap the `faster_whisper.WhisperModel` class. Instead of running actual inference, the mock should return predefined `Segment` objects based on the input length.
-   **Model Registry Mock:** Mock the download logic to verify that the daemon correctly handles missing models, failed downloads, and invalid paths without actually hitting Hugging Face servers in CI.

### 4.2 Hardware-Dependent vs. Agnostic Tests
-   **CPU-Only CI:** CI environments (GitHub Actions) usually lack GPUs. Tests should be written to default to `device="cpu"` and `compute_type="int8"` to ensure they can run in standard pipelines.
-   **Hardware Tags:** Use `pytest` markers (e.g., `@pytest.mark.gpu`) to skip GPU-specific tests unless a GPU is detected.

### 4.3 End-to-End Audio Simulation
-   **WAV Replay:** Create a test utility that feeds a high-quality `.wav` file into the daemon's audio queue chunk-by-chunk, simulating real-time input.
-   **Ground Truth Comparison:** Compare the streamed output against a "ground truth" text file to measure Word Error Rate (WER) and Latency in a controlled environment.

---

## 5. Roadmap

| Phase | Milestone | Description |
| :--- | :--- | :--- |
| **Phase 1** | **Local Batch** | Replace API call with local `faster-whisper` (record -> stop -> transcribe locally). |
| **Phase 2** | **Config & Management** | Implement `.harp.yaml` integration and automated model downloading. |
| **Phase 3** | **Streaming Backbone** | Implement the concurrent audio queue and VAD-triggered transcription. |
| **Phase 4** | **UX & Feedback** | Implement real-time typing/display of finalized segments. |
| **Phase 5** | **Context Integration** | Finalize "Clipboard Context" injection and dynamic prompt updates. |
