# Record-and-Stream & Early Upload Strategies for Harpa

This document outlines strategies for implementing low-latency audio transcription in Harpa (harp), focusing on "Record-and-Stream" techniques, early upload strategies, and the optimal use of providers like OpenRouter, Groq, and Deepgram.

## 1. Best Practices for Uploading while Recording (Chunking)

To minimize the "wait time" after a user stops speaking, audio should be processed in chunks during the recording process.

### Chunking Strategies
*   **VAD-Based Chunking (Recommended):** Use Voice Activity Detection (VAD) to detect natural pauses (200–500ms of silence). Upload the segment as soon as a pause is detected. This ensures that words are not cut in half, which is critical for transcription accuracy.
    *   *Tools:* `Silero VAD` (highly accurate, deep-learning based) or `WebRTC VAD` (lightweight and fast).
*   **Fixed-Time Chunking with Overlap:** If VAD is too complex, use fixed intervals (e.g., every 10–20 seconds). Always include a **1–2 second overlap** with the previous chunk to provide context to the model and avoid losing words at the boundaries.
*   **Sequence Management:** Each chunk must be sent with a sequence ID. If using a stateless API, the client must manage the reassembly of the transcript or provide the previous chunk's transcript as a "prompt" to the next request.

## 2. Early Upload with Base64 APIs (OpenRouter)

OpenRouter’s multimodal models (like Gemini 2.0 Flash or GPT-4o-audio) require the full audio data to be sent as a base64-encoded string within a single message. Since OpenRouter does not currently support a persistent WebSocket for streaming input, "early upload" must be handled via a **Background Accumulation Strategy**:

1.  **Concurrent Encoding:** While recording, encode the audio into a compressed format (like Opus) in a background thread.
2.  **Base64 Prefetching:** As chunks are finalized (via VAD), convert them to base64 and store them in an array.
3.  **The "Final Sprint" Request:** As soon as the user stops recording:
    *   Encode the final (short) chunk.
    *   Concatenate the base64 strings (if the provider supports multi-part or if you are sending the whole file).
    *   **Note:** Most providers require a single valid audio file. To "stream" to these, you actually send **intermediate requests** for each chunk to get partial results, or wait until the end to send the full file.
    *   *Optimization:* If you send chunks sequentially to an LLM, you can include the transcript of the previous chunk in the system prompt to maintain context.

## 3. Proxy & Staging Upload Strategies

Since OpenRouter does not support pre-uploading to a URL, a "proxy" strategy involves moving the data closer to the inference engine during recording.

### Staging Strategy
*   **Local Proxy:** A local background worker that starts the base64 conversion and HTTP connection initialization as soon as the first chunk is ready.
*   **Middle-man Server (Advanced):**
    *   Stream raw audio to a lightweight staging server (e.g., using WebSockets or gRPC) during recording.
    *   The staging server accumulates the audio and, upon receiving the "stop" signal, immediately forwards the data to OpenRouter/Groq.
    *   This shifts the bandwidth-heavy upload from the final "stop" moment to the "during recording" phase, effectively hiding the upload latency.

## 4. Optimal Audio Formats & Codecs

Choosing the right codec is a trade-off between upload speed (bandwidth) and transcription accuracy.

| Format | Compression | Latency | Accuracy | Recommendation |
| :--- | :--- | :--- | :--- | :--- |
| **Opus** | **Excellent (1:10)** | **Ultra-Low (<26ms)** | **High (~2% loss)** | **Best Choice.** Designed for VoIP/Streaming. |
| **WAV (PCM16)**| None | Zero | Highest | Use for local transcription only. Too large for fast cloud upload. |
| **FLAC** | Good (1:2) | Low | Highest | Best for high-accuracy batch processing. |
| **MP3** | Good | High (>100ms) | Fair (~10% loss) | **Avoid.** High encoding latency and artifacting. |

**Technical Spec:** For most STT engines, **16kHz Mono** is the optimal sampling rate. Higher rates (44.1kHz+) increase file size without significantly improving transcription accuracy for speech.

## 5. Leveraging Direct Providers (Groq & Deepgram)

While OpenRouter provides a unified interface, direct providers offer specialized "fast-path" features:

### Groq (Whisper-Large-V3-Turbo)
*   **Strength:** Raw inference speed. Groq can transcribe 10 minutes of audio in ~3 seconds.
*   **Application:** Best for "Push-to-Talk" dictation. Even without true streaming, the "wait" after a 30-second recording is nearly instantaneous.
*   **Strategy:** Use Groq for the initial "Fast Transcript," then send that text to an LLM (via OpenRouter) for processing/refinement.

### Deepgram (Nova-3)
*   **Strength:** Native WebSocket streaming with "Interim Results."
*   **Application:** Best for real-time applications where you want to see the text appear *word-by-word* as you speak.
*   **Latency:** Sub-300ms Time-to-First-Word.

### Integration with Harpa
To achieve the fastest user experience, Harpa should:
1.  **Record in Opus** at 16kHz Mono.
2.  **Stream chunks to Groq** (or a local `faster-whisper` instance) as they are finalized by VAD.
3.  **Display partial transcripts** immediately to the user.
4.  **Finalize with OpenRouter** only if complex reasoning (like "fix my grammar" or "summarize this") is required, using the already-transcribed text to save on multimodal costs.
