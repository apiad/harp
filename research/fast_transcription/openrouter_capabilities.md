# OpenRouter Audio Transcription Capabilities: Speed and Latency Analysis

This report investigates OpenRouter's capabilities for audio transcription, focusing on models, latency, streaming support, and optimization strategies.

## 1. Available Audio Models and Latency

OpenRouter provides access to several "multimodal" models that support audio input. Unlike dedicated Speech-to-Text (STT) services, these models process audio within a chat context, allowing for simultaneous transcription and reasoning.

### Lowest Latency Models (Estimated TTFT)
| Model | Provider(s) | TTFT (s) | Throughput (tok/s) | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Voxtral Small 24B** | Mistral/Various | **0.14s - 0.37s** | 70 - 100+ | Native audio support; extremely fast start times. |
| **Gemini 2.0 Flash Lite** | Google | **< 0.50s** | 80+ | Optimized for speed and high-volume tasks. |
| **Gemini 2.0 Flash** | Google | **0.64s - 0.72s** | 50 - 70 | High accuracy with low latency. |
| **GPT-4o Audio Preview** | OpenAI | **0.82s** | 45 - 68 | High quality, slightly higher latency than Gemini Flash. |

### Dedicated STT Models
While OpenRouter primarily focuses on the `/v1/chat/completions` endpoint, some providers proxied by OpenRouter (like DeepInfra or Groq) offer Whisper models. However, access is typically limited to the chat interface (sending audio as base64) rather than a dedicated transcription endpoint.

## 2. Streaming and Upload Support

### Streaming Audio Input
*   **Not Supported Natively:** OpenRouter does **not** currently support WebSocket-based streaming audio input (similar to OpenAI's Realtime API).
*   **Base64 Requirement:** All audio must be sent as a complete, base64-encoded string within the `messages` array of a standard HTTP POST request.

### Chunked Uploads
*   **Manual Chunking:** For large files or pseudo-streaming, users must split audio into segments (e.g., 5-10 second chunks) and send them as individual requests.
*   **Context Management:** To maintain accuracy across chunks, previous transcripts should be included in the chat history to provide context for the model.

### Streaming Output
*   **Supported:** OpenRouter supports `stream: true` for the **text response**. This allows users to receive the transcript as it is being generated, reducing perceived latency.

## 3. Performance Metrics (TTFT & Total Time)

The performance of audio tasks on OpenRouter is influenced by model complexity and the underlying provider's infrastructure.

*   **Time To First Token (TTFT):** For fast models like **Voxtral** or **Gemini Flash**, TTFT is often sub-700ms.
*   **End-to-End (E2E) Latency:** For a standard 10-20 second audio clip, E2E latency typically ranges from **1.2s to 2.5s**, depending on the model and provider routing.
*   **File Size Impact:** Since audio is sent base64-encoded, large files increase payload size and transmission time. A 1MB audio file (roughly 1 minute of compressed audio) adds minimal overhead, but 25MB+ files can significantly delay the start of processing.

## 4. Optimization: Speed vs. Accuracy

OpenRouter provides specific parameters to prioritize speed:

### The `:nitro` Suffix
Appending `:nitro` to a model ID (e.g., `google/gemini-2.0-flash:nitro`) instructs OpenRouter to route the request to the provider with the **highest throughput** currently available.

### Provider Sorting
In the request body, you can explicitly request the lowest-latency provider:
```json
{
  "model": "google/gemini-2.0-flash",
  "provider": {
    "sort": "latency"
  },
  "messages": [...]
}
```
*   **`sort: "latency"`**: Prioritizes Time To First Token.
*   **`sort: "throughput"`**: Prioritizes how fast the full transcript is generated.

### "Flash" and "Lite" Models
Always prefer "Flash" or "Lite" variants for transcription. Models like `google/gemini-2.0-flash-lite` are specifically architected for lower latency.

## 5. OpenRouter Routing vs. Direct API Calls

### Gateway Overhead
OpenRouter adds a small processing hop at the edge (via Cloudflare Workers), typically adding **25ms to 40ms** of latency. 

### Comparison with Direct Providers
| Provider | Native Protocol | Best For | Latency vs OpenRouter |
| :--- | :--- | :--- | :--- |
| **Deepgram** | WebSocket / REST | Real-time Streaming | **Significantly Faster** (<300ms) |
| **Groq** | REST (Whisper) | High-speed Batch | **Faster** (No gateway overhead) |
| **OpenRouter** | REST (Multimodal) | Reasoning + Transcription | **Slower** (+40ms gateway + LLM overhead) |

### Summary Comparison
*   **Direct (Groq/Deepgram):** Use if you need *pure transcription* at maximum speed. They support dedicated STT endpoints (`/v1/audio/transcriptions` or `/v1/listen`) which are optimized for audio processing.
*   **OpenRouter:** Use if you need to *interact* with the audio (e.g., "Summarize this call" or "What did the person say about X?") in a single step. OpenRouter does not currently support the standard OpenAI-compatible transcription endpoint for its faster providers (Groq/Deepgram).

## Conclusion and Recommendations

For the fastest transcription via OpenRouter:
1. Use **`google/gemini-2.0-flash-lite:nitro`** or **`mistralai/voxtral-small-24b`**.
2. Set **`stream: true`** in your request.
3. Explicitly set **`provider.sort: "latency"`** in the JSON body.
4. Keep audio segments short (under 30s) to minimize base64 payload transmission.
5. If true real-time (sub-500ms E2E) is required, consider direct integration with **Deepgram** instead of an LLM gateway.
