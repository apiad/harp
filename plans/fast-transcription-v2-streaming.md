# Implementation Plan: Fast Transcription V2 (Real-time Streaming)

This plan outlines the transition from a sequential "Record-then-Upload" model to a concurrent "Stream-while-Recording" architecture using `httpx`, `pylibopus`, and OpenRouter's multimodal streaming capabilities.

## Objective
Reduce perceived and actual latency of Harpa's transcription by:
1. Encoding audio to Opus in 20ms frames during recording.
2. Initiating the API request immediately when recording starts.
3. Streaming the audio payload as it's being recorded.
4. Printing response tokens in real-time.

## Architectural Impact
- **Network**: Replaces `openai` SDK with a custom `httpx.AsyncClient` utilizing HTTP/2 for multiplexing and connection persistence.
- **Audio Pipeline**: Moves from batch PCM processing to a producer-consumer model using a background thread for Opus encoding.
- **Concurrency**: The `HarpoDaemon` will manage an active `httpx` request task that runs in parallel with the audio capture loop.
- **Data Flow**: `Microphone -> PCM -> Opus (20ms frames) -> Base64 -> HTTP Generator -> OpenRouter`.

## File Operations

### Modified Files
- `src/harp/api.py`: Replace `OpenRouterClient` logic with manual `httpx` streaming implementation.
- `src/harp/audio.py`: Integrate `pylibopus` and update `AudioStreamer` for real-time chunking.
- `src/harp/daemon.py`: Refactor `_start_recording` and `_stop_recording` to manage the streaming request life cycle.
- `pyproject.toml`: Add `pylibopus` and `httpx[http2]` to dependencies.

### New Files
- `tests/benchmark_latency_v2.py`: Automated benchmarking tool for E2E latency.

## Step-by-Step Execution

### Step 1: Update Dependencies
- Add `pylibopus` and `httpx[http2]` to `pyproject.toml`.
- Note: `pylibopus` requires `libopus` to be installed on the system.

### Step 2: Implement Real-time Opus Encoding in `audio.py`
- Modify `AudioStreamer` to accept an `asyncio.Queue` (or a thread-safe `queue.Queue`).
- Initialize a `pylibopus.Encoder` (16kHz, Mono, VOIP mode).
- In the `sounddevice` callback:
  1. Accumulate PCM samples until a 20ms frame (320 samples at 16kHz) is reached.
  2. Encode the frame to Opus.
  3. Convert the Opus bytes to a Base64 segment.
  4. Put the Base64 segment into the queue.

### Step 3: Refactor `api.py` for Streaming
- Create a persistent `httpx.AsyncClient(http2=True)`.
- Implement `stream_transcribe` method:
  - Takes a generator (or queue iterator) that yields Base64 audio chunks.
  - Constructs the JSON body: `{"model": "...", "stream": true, "messages": [...]}`.
  - The `user` message `content` list will contain the static text instructions followed by the audio parts.
  - *Optimization*: Use a generator for the request body to stream the JSON structure itself, injecting audio chunks into the `url` field of the audio content type.
  - Use `client.stream("POST", ...)` to handle the response stream.

### Step 4: Optimize Prompt Engineering
- Ensure `system` message and static `user` instructions are at the beginning of the messages array.
- Place the `input_audio` (or the multimodal audio object) as the **last** element in the content array.
- Set `provider.sticky: true` in the OpenRouter specific parameters to favor cache hits on the prefix.

### Step 5: Update `daemon.py` Logic
- **`_start_recording`**: 
  - Initialize the `AudioStreamer` with a queue.
  - Start the `api_client.stream_transcribe` task as a background `asyncio.Task`.
- **Token Processing**:
  - The background task should iterate over the response stream and print tokens to `self.console` (Harpa daemon stdout) immediately.
- **`_stop_recording`**:
  - Signal the audio queue to close (EOF).
  - Wait for the transcription task to complete.
  - Capture the final concatenated text for typing.

### Step 6: Benchmarking Suite
- Create `tests/benchmark_latency_v2.py`.
- Measure:
  - **Stop-to-First-Token (STFT)**: Time between the user releasing the hotkey and the first character appearing in the terminal.
  - **Stop-to-Last-Token (STLT)**: Time until the full transcription is ready for typing.
  - Compare these metrics against the V1 implementation.

## Testing Strategy
1. **Unit Test**: Verify the Opus encoder produces valid packets that can be decoded back to audible PCM.
2. **Integration Test**: Mock the `httpx` response to ensure the generator-based request body is correctly formatted (valid JSON structure while streaming).
3. **Live Test**: Run the daemon and verify that tokens appear in the terminal *before* the recording is even finished (if using models with very low TTFT) or immediately after stopping.
4. **Latency Profile**: Use the benchmark script to confirm that the "Stop-to-First-Token" is significantly reduced (target < 500ms).
