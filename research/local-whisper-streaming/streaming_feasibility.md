# Streaming Technical Feasibility for Whisper.cpp

This report evaluates the technical feasibility of integrating real-time streaming transcription using `whisper.cpp` into a Python-based daemon (Harp).

## 1. Python Bindings and IPC Methods

For integrating `whisper.cpp` into a daemon, three primary methods were evaluated:

### A. pywhispercpp (Recommended for Library Integration)
*   **Description:** High-level Pythonic bindings for `whisper.cpp`.
*   **Key Features:**
    *   **Direct Callbacks:** Supports `new_segment_callback` to receive partial results as they are finalized.
    *   **Low Latency:** Runs the C++ core directly, releasing the GIL during inference.
    *   **Built-in Examples:** Includes a `LiveStream` class and `Assistant` examples.
*   **Best For:** Deep integration into a Python daemon where you need programmatic control over the transcription lifecycle.

### B. whisper-cpp-python
*   **Description:** Inspired by `llama-cpp-python`, focuses on an OpenAI-compatible FastAPI server.
*   **Key Features:**
    *   Provides a ready-made HTTP server.
    *   Less flexible for custom real-time audio pipelines within the same process.
*   **Best For:** Microservice architectures where the transcriber runs in a separate container/process and communicates via HTTP.

### C. whisper.cpp Native Server (`server.cpp`)
*   **Description:** A lightweight C++ HTTP server included in the `whisper.cpp` repository.
*   **Pros:** Minimal overhead, extremely fast.
*   **Cons:** Request-response based (not optimized for streaming audio chunks via WebSockets); requires external management of audio files/segments.
*   **Best For:** Simple "send file, get text" workflows.

**Conclusion:** `pywhispercpp` is the most feasible choice for Harp's daemon-based architecture as it allows for direct memory access to audio buffers and fine-grained callback handling without the overhead of HTTP.

---

## 2. Implementation Patterns: Silero VAD + Streaming Whisper

Combining **Silero VAD** with `whisper.cpp` is essential to prevent "hallucinations" during silence and to reduce CPU load.

### Pattern 1: The "Gatekeeper" (Segment-Based)
The VAD acts as a trigger to capture a full utterance before sending it to Whisper.
1.  Capture audio in 32ms chunks (512 samples at 16kHz).
2.  If VAD detects speech, start buffering.
3.  If VAD detects silence for $>500ms$, send the entire buffer to `whisper.cpp`.
4.  **Pros:** Highest accuracy; avoids hallucinations.
5.  **Cons:** Latency is equal to the length of the sentence plus inference time.

### Pattern 2: The "Sliding Window" (Real-Time Feedback)
Whisper processes a rolling buffer to provide text *while* the user is speaking.
1.  Maintain a 5-second rolling buffer.
2.  Every 500ms, send the current buffer to `whisper.cpp`.
3.  Use `new_segment_callback` to update the UI with "partial" results.
4.  When VAD detects the "final" end of speech, perform a final pass and clear the buffer.
5.  **Pros:** Low perceived latency (text appears instantly).
6.  **Cons:** Higher CPU usage; text may change slightly as more context is gathered.

---

## 3. Partial vs. Final Results Handling

`whisper.cpp` is an encoder-decoder model, meaning it doesn't emit tokens one by one like a GPT model. Instead, it emits **segments**.

*   **Partial Results:** In a "Sliding Window" approach, the results from the current inference pass are treated as "partial." In the UI/CLI, these can be overwritten or displayed in a "dimmed" state.
*   **Final Results:** Once the VAD identifies a significant pause or the "end of speech" event, the transcription for that segment is marked as "final" and injected into the target application.
*   **UI Implementation:**
    *   **CLI:** Use `\r` (carriage return) to overwrite the current line with updated partial text.
    *   **Daemon:** Emit a "partial" event to the UI and a "final" event for keyboard emulation.

---

## 4. Threading and Async Constraints

Real-time audio processing in Python faces significant challenges due to the Global Interpreter Lock (GIL) and the CPU-heavy nature of Whisper.

### Constraints & Solutions
1.  **Audio Capture (I/O-bound):** Use `sounddevice`. It captures audio in a C-level thread. As long as the callback is fast, the GIL won't cause drops.
2.  **Whisper Inference (CPU-bound):** This will peg CPU cores at 100%. If run in the same thread as the UI or capture, it will cause "stuttering."
    *   **Solution:** Use `pywhispercpp` which releases the GIL during inference, or run inference in a separate `multiprocessing.Process`.
3.  **Input Injection:** Keyboard emulation (e.g., via `pynput` or `uinput`) is lightweight but must be synchronized to ensure text is injected into the correct window.

### Recommended Architecture
*   **Thread 1 (Capture):** `sounddevice` InputStream callback. Pushes raw 16kHz NumPy arrays to a Queue.
*   **Thread 2 (VAD):** Processes the Queue, detects speech boundaries, and aggregates chunks.
*   **Thread 3 (Inference):** Consumes speech segments from the VAD, calls `whisper.cpp`, and handles the `new_segment_callback`.
*   **Async Loop:** The daemon's main loop (e.g., `asyncio`) manages the lifecycle and communication between these threads.

---

## 5. Summary Table

| Component | Technology | Role |
| :--- | :--- | :--- |
| **Audio Capture** | `sounddevice` | Low-latency 16kHz mono capture. |
| **VAD** | Silero VAD | Filter silence and noise; trigger inference. |
| **Whisper Core** | `whisper.cpp` (via `pywhispercpp`) | High-performance local inference. |
| **Concurrency** | `threading` + GIL release | Separate capture and inference. |
| **Feedback** | `new_segment_callback` | Provide real-time partial text. |
| **IPC** | Local Library Call | Direct integration for minimal latency. |
