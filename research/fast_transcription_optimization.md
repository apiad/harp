# Harpa Transcription Speed Optimization Report

## Executive Summary
This research identifies a path to transition Harpa from its current sequential transcription model to an ultra-fast, concurrent architecture. By leveraging OpenRouter's lowest-latency multimodal models (**Gemini 2.0 Flash Lite** and **Voxtral**) and implementing a **Background Accumulation Strategy**, Harpa can achieve near-instantaneous transcription. The key is to **encode audio to Opus in real-time** and maintain a **background base64 buffer** during recording, ensuring the API request is ready for submission the moment the user stops speaking. Additional optimizations like **Prompt Caching** (via `provider.sticky: true`) and **HTTP/2 multiplexing** further reduce the "perceived" latency, making the transcription experience feel seamless and high-speed.

## Research Questions

### 1. OpenRouter Audio Transcription Capabilities & Performance
*   **Fastest Models:** **Voxtral Small 24B** (TTFT ~0.14s-0.37s) and **Gemini 2.0 Flash Lite** (TTFT < 0.50s) are currently the leading low-latency options on OpenRouter.
*   **Input Method:** OpenRouter requires audio to be **base64-encoded** and sent via the standard `/v1/chat/completions` endpoint. It does **not** support WebSocket-based streaming input or dedicated `/v1/audio/transcriptions` endpoints for most providers.
*   **Latency & Performance:** Total E2E latency for short clips is typically between **1.2s and 2.5s**. OpenRouter's gateway adds a minimal overhead of **25ms to 40ms**.
*   **Optimization:** Users can prioritize speed by using the **`:nitro`** model suffix (e.g., `google/gemini-2.0-flash:nitro`) or setting the **`provider.sort: "latency"`** parameter in the request body.
*   **Direct vs. Gateway:** Direct API calls to **Deepgram** (for real-time streaming) or **Groq** (for Whisper batch speed) remain significantly faster than routing through OpenRouter's multimodal LLM interface for pure transcription tasks.

Detailed report: [openrouter_capabilities.md](fast_transcription/openrouter_capabilities.md)

### 2. "Record-and-Stream" Architecture (Early Upload)
*   **Best Practices for Chunking**: Recommended using **VAD-based chunking** (Voice Activity Detection) to split audio at natural silence breaks (200-500ms). Alternatively, fixed-time chunking with a 1-2 second overlap ensures continuity.
*   **Early Upload with OpenRouter**: Since OpenRouter requires single base64 messages for multimodal models, the best approach is a **Background Accumulation Strategy**. Encode audio to Opus and convert to base64 in a background thread while recording, then fire the final request immediately upon "stop".
*   **Proxy/Staging Strategy**: Streaming audio chunks to a **local proxy or staging server** during recording can hide upload latency, making the final API call feel instantaneous.
*   **Optimal Audio Formats**: **Opus** is the clear winner, offering excellent compression (10x smaller than WAV), low latency (<26ms), and near-perfect transcription accuracy (only ~2% degradation). **16kHz Mono** is the recommended technical specification.
*   **Direct Providers**: **Groq (Whisper-Large-V3-Turbo)** is identified as the fastest for batch/segmented processing, while **Deepgram (Nova-3)** is superior for true real-time word-by-word streaming.

Detailed report: [streaming_strategies.md](fast_transcription/streaming_strategies.md)

### 3. Efficient Custom Prompting & Prompt Engineering
*   **Prompt Length vs. Latency:** TTFT increases linearly with token count in the `system_message` or `user` text. For multimodal LLMs, the entire prompt must be "prefilled" before generation begins.
*   **Top Models for Speed:** **Voxtral Small 24B** (sub-200ms - 500ms TTFT) and **Gemini 2.5/3.1 Flash Lite** (approx. 380ms TTFT) are significantly faster than standard "Pro" or "Large" models.
*   **Dynamic Context Strategy:** To maintain low latency, dynamic context (like clipboard or window titles) should be **appended** at the end of the message array. Placing it at the beginning invalidates **Prompt Caching**, which can otherwise reduce TTFT by up to 31%.
*   **OpenRouter Parameters:** 
    - `provider.sticky: true` is essential for maximizing cache hits.
    - `provider.quantizations: ["int4"]` can prioritize faster, lower-precision models.
    - `stream: true` is the best way to reduce "perceived" latency for the user.
*   **Prompt-Heavy vs. Prompt-Light:** Complex instructions (Prompt-Heavy) can add 50-200ms of overhead compared to simple transcription instructions (Prompt-Light).

Detailed report: [prompt_optimization.md](fast_transcription/prompt_optimization.md)

### 4. Network & Implementation Optimizations
*   **Asynchronous Recording & Encoding:** Use a producer-consumer pattern where `sounddevice`'s non-blocking callback feeds a `queue.Queue`. A background worker encodes PCM to Opus in real-time while recording is active.
*   **Streaming Uploads:** Use `httpx` or `aiohttp` with a generator/iterator as the request body to perform a "pre-flight" POST request. This allows uploading audio chunks as they are encoded, overlapping the network upload with the recording phase.
*   **Connection Optimization:** Use `httpx` with `http2=True` to enable multiplexing and minimize TLS handshakes. Reuse a single `AsyncClient` to keep connections "warm" and persist DNS/SSL state.
*   **Overlapping Processing:** By using 20ms Opus frames and encoding them immediately, the final audio file is ready for transcription the moment the user stops speaking.
*   **Optimized Library Stack:**
    - **`sounddevice`**: Superior for low-latency callback-driven audio capture.
    - **`pylibopus`**: Efficient, low-latency codec optimized for speech.
    - **`httpx`**: Modern async client with native HTTP/2 support.
    - **`numpy`**: Fast buffer transformations (e.g., float to int16) before encoding.

Detailed report: [network_implementation.md](fast_transcription/network_implementation.md)

## Conclusions
The research confirms that Harpa's transcription speed can be significantly improved by moving from a sequential "Record -> Save -> Upload -> Transcribe" workflow to a highly concurrent "Stream -> Encode -> Accumulate -> Transcribe" architecture. 

Key findings include:
*   **Optimal Models:** **Voxtral Small 24B** and **Gemini 2.0 Flash Lite** are the speed champions on OpenRouter, offering sub-500ms TTFT.
*   **Latency Drivers:** The primary bottlenecks are the "Stop-to-Start" delay (encoding/uploading after recording ends) and the lack of native WebSocket streaming on OpenRouter.
*   **Optimization Levers:** Real-time Opus encoding and background base64 accumulation can hide almost all upload and processing latency. Prompt caching is critical for maintaining performance when using custom system prompts.

## Recommendations
1.  **Adopt a Concurrent Audio Pipeline:** Implement a producer-consumer pattern in the daemon using `sounddevice` and `pylibopus` to encode audio to Opus in 20ms frames *while* recording.
2.  **Simulate Streaming via Background Accumulation:** Maintain a background base64 buffer of the encoded Opus stream so the final payload is ready for submission the millisecond recording stops.
3.  **Optimize OpenRouter Configuration:**
    *   Default to `google/gemini-2.0-flash:nitro` or `mistralai/pixtral-12b:nitro` for the best speed/quality balance.
    *   Use `provider.sticky: true` and `provider.sort: "latency"`.
4.  **Strategic Prompt Engineering:** Keep static instructions in the `system_message` and append dynamic context (clipboard, window titles) at the very end of the user message to maximize **Prompt Caching** hits.
5.  **Network-Level Warm-up:** Use a persistent `httpx.AsyncClient` with `http2=True` in the daemon to avoid DNS and TLS handshake overhead on every request.
