# Implementation Plan: High-Speed Concurrent Transcription Architecture

This plan outlines the transition of Harpa from a sequential "Record-then-Process" model to a high-performance, concurrent "Stream-and-Encode" architecture. By leveraging real-time Opus encoding, background accumulation, and optimized network persistent connections, we aim to reduce end-to-end transcription latency by over 50%.

## Objective
Transform Harpa into an ultra-fast transcription tool with near-instantaneous response times (targeting < 1.5s E2E) by implementing concurrent audio processing, HTTP/2 multiplexing, and optimized LLM prompting.

## Architectural Impact
- **Audio Pipeline:** Moves from bulk WAV processing to frame-by-frame Opus encoding (20ms frames) using a producer-consumer pattern.
- **Network Layer:** Replaces the standard OpenAI client's default transport with a persistent `httpx.AsyncClient` supporting HTTP/2 and connection pooling.
- **Provider Optimization:** Switches to Gemini 2.0 Flash via OpenRouter with latency-optimized routing and prompt caching.
- **Concurrency Model:** Uses a background encoder thread to offload processing from the audio capture and main event loops.

## File Operations

### Existing Files to Modify:
- `pyproject.toml`: Add `pylibopus` and `httpx[http2]` dependencies.
- `src/harp/config.py`: Update default model and OpenRouter settings.
- `src/harp/api.py`: Refactor `OpenRouterClient` for persistent HTTP/2 and Opus support.
- `src/harp/audio.py`: Implement concurrent `AudioStreamer` with real-time encoding.
- `src/harp/daemon.py`: Manage client lifecycle and optimize prompt construction for caching.

### New Files to Create:
- `tests/benchmark_latency.py`: A specialized script to measure Stop-to-Result latency.

---

## Step-by-Step Execution

### Step 1: Baseline Benchmarking
**Goal:** Establish current performance metrics.
- Create `tests/benchmark_latency.py` that:
    1. Records a 5-second sample.
    2. Measures the time from the "Stop" signal to the arrival of the transcription.
    3. Runs 5 trials and reports average/p95 latency.

### Step 2: Update Dependencies and Configuration
**Goal:** Prepare the environment for the new features.
- Update `pyproject.toml` to include:
    - `pylibopus` (or `opuslib` as fallback)
    - `httpx[http2]`
- Update `src/harp/config.py`:
    - Set `api_model` default to `google/gemini-2.0-flash:nitro`.
    - Add `api_sticky: bool = True` and `api_sort: str = "latency"`.

### Step 3: Implement Persistent HTTP/2 API Client
**Goal:** Minimize network overhead via connection reuse and multiplexing.
- Refactor `src/harp/api.py`:
    - Initialize a single `httpx.AsyncClient(http2=True)` inside `OpenRouterClient`.
    - Pass this client to the `AsyncOpenAI` constructor.
    - Update the `transcribe` method:
        - Change audio format from `wav` to `opus`.
        - Pass `provider: {"sticky": True, "sort": "latency"}` in `extra_body`.
        - Accept pre-encoded base64 data instead of raw numpy arrays.

### Step 4: Concurrent Audio Pipeline & Opus Encoding
**Goal:** Encode audio in real-time to eliminate the "Encoding/Saving" delay after recording stops.
- Refactor `src/harp/audio.py`:
    - Introduce a `threading.Thread` and `queue.Queue` for the background encoder.
    - Implement the encoder loop:
        1. Consume float32 chunks from the `sounddevice` callback.
        2. Convert to int16 PCM.
        3. Segment into 20ms frames (320 samples at 16kHz).
        4. Encode to Opus using `pylibopus`.
        5. Accumulate encoded bytes in a thread-safe buffer.
    - Add `get_encoded_payload()` which returns the base64-encoded Opus buffer.

### Step 5: Refactor Daemon Logic
**Goal:** Integrate the concurrent pipeline and optimize prompt caching.
- Update `src/harp/daemon.py`:
    - Initialize the `OpenRouterClient` once at startup and ensure it is properly closed during cleanup.
    - Modify `_stop_recording`:
        - Retrieve the base64 Opus payload from `audio_streamer` immediately.
        - Call `api_client.transcribe` using the pre-ready payload.
    - **Prompt Caching Optimization**: Structure the messages array to maximize cache hits:
        1. System Message (Static instructions).
        2. User Message: Instruction (Static transcription/command text).
        3. User Message: Audio Data (Dynamic).
        4. User Message: Clipboard Context (Dynamic - *appended at the very end*).

---

## Testing Strategy

### 1. Functional Testing
- Verify that Opus encoding produces valid audio (can be decoded and played back for debugging).
- Ensure clipboard context is correctly appended and recognized by the model.
- Confirm that the `:nitro` suffix and provider sorting are being passed correctly in the API request.

### 2. Performance Testing
- Run `tests/benchmark_latency.py` and compare against the baseline.
- Expected Result: Significant reduction in "Post-Stop" delay (from ~1.5s-3s down to < 1s for the processing start).

### 3. Connection Stability
- Verify that the `httpx` client successfully uses HTTP/2 multiplexing (can be checked via `httpx` logs or environment variables).
- Ensure the connection persists between multiple transcription attempts.

### 4. Error Handling
- Validate behavior when `libopus` is missing on the system (provide helpful error messages).
- Ensure the encoder thread shuts down gracefully if an error occurs during recording.
