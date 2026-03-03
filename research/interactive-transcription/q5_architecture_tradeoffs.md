# Interactive Transcription Architecture Trade-offs

This report evaluates the performance, cost, and architectural trade-offs for interactive transcription systems, comparing cloud providers (OpenAI, Google, OpenRouter) and local-first solutions.

## 1. Latency Benchmarks (RTT for 2s Audio Payloads)

Round Trip Time (RTT) for short audio bursts is the critical metric for "interactive" feel. For a **2-second audio payload**, the following table summarizes typical performance:

| Service | Average RTT | Performance Profile |
| :--- | :--- | :--- |
| **Google Gemini 1.5 Flash** | **400ms – 800ms** | **Fastest.** Native multimodal processing (no separate ASR-to-LLM handoff). Optimized for sub-second response. |
| **OpenRouter (via Flash)** | **600ms – 1,000ms** | **Variable.** Adds a "gateway tax" of 100ms–200ms. Latency depends on the underlying provider (AI Studio vs. Vertex). |
| **OpenAI Whisper-1** | **800ms – 1,500ms** | **Moderate.** Reliable and high accuracy, but traditional architecture and API overhead make it slower than "Flash" models. |

### Key Findings:
- **Multimodal Speed:** Gemini 1.5 Flash is consistently faster because it processes audio tokens directly rather than performing a discrete transcription step.
- **Network Overhead:** For 2s payloads, the network handshake and "time-to-first-byte" represent a significant percentage of total RTT. Direct provider access (Google AI Studio) is ~150ms faster than OpenRouter.

---

## 2. Cost Analysis: High-Frequency Session

**Scenario:** 1 hour of active speaking, sending an audio chunk every **1.5 seconds**.
- **Total Requests:** 2,400 requests/hour.
- **Total Audio Duration:** 60 minutes.

| Provider | Pricing Model | Cost per 1.5s Chunk | Total Cost (1 Hour) |
| :--- | :--- | :--- | :--- |
| **OpenAI Whisper-1** | $0.006 / minute | ~$0.00015 | **$0.36** |
| **Google Gemini 1.5 Flash** | $0.075 / 1M tokens | ~$0.0000036 | **$0.0086** |
| **OpenRouter (Flash)** | Passthrough (~$0.075/1M) | ~$0.0000036 | **$0.0086** |
| **Local (Faster-Whisper)** | Infrastructure only | $0.00 | **$0.00** |

### Critical Insight:
- **Minimum Billing:** Unlike Deepgram (15s minimum) or traditional Telco APIs, OpenAI and Google Gemini **do not** have high minimum billing durations per request for these specific endpoints. OpenAI bills to the nearest second; Gemini bills per token (32 tokens/sec).
- **Gemini Dominance:** Gemini 1.5 Flash is approximately **40x cheaper** than OpenAI Whisper-1 for this high-frequency use case.

---

## 3. Local-First vs. Cloud-Hybrid Comparison

| Feature | Local-First (Whisper.cpp / Faster-Whisper) | Cloud-Hybrid (Local VAD + Cloud STT) |
| :--- | :--- | :--- |
| **Network Latency** | **0ms** (Instant start) | 200ms – 1,000ms (Network dependent) |
| **Hardware Req.** | High (Requires GPU or Apple Silicon) | Low (Runs on any device) |
| **Privacy** | **Maximum** (Data never leaves device) | Moderate (Audio sent to cloud) |
| **Accuracy** | Dependent on local model (Small/Medium) | High (Always uses "Large" equivalent) |
| **Operating Cost**| $0 (Electricity only) | Per-minute / Per-token API fees |

### Hardware Benchmarks (Real-Time Factor - RTF):
*RTF < 1.0 means faster than real-time.*

- **NVIDIA RTX 3060 (Faster-Whisper):**
    - `Small` model: ~0.08 RTF (12x real-time)
    - `Large-v3` model: ~0.25 RTF (4x real-time)
- **Apple M1 (Whisper.cpp):**
    - `Small` model: ~0.12 RTF (8x real-time)
    - `Large-v3` model: ~0.60 RTF (1.6x real-time)

---

## 4. Impact of Regional Latency & Local VAD

Using a local server or client-side component for **VAD (Voice Activity Detection)** and pre-processing is the single most effective way to improve responsiveness.

### Benefits of Local VAD:
1.  **Latency Reduction (200ms – 800ms):**
    - Local VAD eliminates the "silence timeout" (the period a cloud server waits to ensure you've stopped talking). 
    - It allows the system to trigger "Stop" and "Process" signals milliseconds after speech ends.
2.  **Cost Reduction (30% – 60%):**
    - In a 1-hour session, actual speech usually occupies only 40-70% of the time.
    - Local VAD ensures **only speech segments** are sent to the API, preventing billing for silence and background noise.
3.  **Accuracy Improvement:**
    - Prevents "hallucinations" that occur when Whisper is forced to transcribe long periods of silence or ambient fan noise.

---

## 5. Practical Advice: 'Low-Cost / High-Responsiveness' Stack

For a production-grade interactive system, the following stack provides the best balance of speed and economy:

### The "Pro-Interactive" Stack:
1.  **VAD Engine:** **Silero VAD** (Local/Client-side).
    - *Why:* Extremely accurate, low CPU usage, avoids sending silence.
2.  **Transcription:** **Google Gemini 1.5 Flash** (via Direct API).
    - *Why:* Lowest RTT (multimodal) and lowest cost ($0.008/hr).
3.  **Fallback/Refinement (Optional):** **Faster-Whisper `distil-small`** (Local).
    - *Why:* Provides "instant" (but slightly less accurate) feedback while the cloud request is in flight. Use the cloud result to "rectify" the local transcript once it arrives.

### Architectural Tip:
- **Avoid WebSockets for Short Bursts:** For 1.5s chunks, the overhead of maintaining a WebSocket is often higher than simple HTTP/2 or gRPC calls to a multimodal model like Gemini. 
- **Use Regional Buckets:** If using Cloud storage for temporary audio buffering, ensure the bucket and the AI model are in the same region (e.g., `us-central1`) to minimize internal Google/AWS transfer latency.
