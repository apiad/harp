# Research Report: Local-First Whisper & Streaming Architecture

## Executive Summary

This research investigates the transition of **Harp** from its current batch, API-driven architecture to a **local-first streaming transcription system** using `whisper.cpp` (or `faster-whisper`). 

**Key findings include:**
- **Significant Latency Reductions:** Moving to local inference (specifically with GPU acceleration and `q5_1` quantization) can reduce transcription latency to **sub-100ms** response times, providing an "instant" user experience compared to the current 2-10s API overhead.
- **Architectural Shift:** To support true streaming, the `HarpDaemon` must transition from a sequential flow to a **concurrent, VAD-driven producer-consumer model**.
- **Local LLM Feasibility:** Running a local LLM like **Llama 3.2 3B** for "Command Mode" is highly viable on modern hardware (8GB+ VRAM) and offers significantly faster **Time to First Token (TTFT)** than cloud APIs.
- **Hybrid Model Recommendation:** A hybrid approach—**Local Whisper for instant transcription + Optional Cloud LLM (OpenRouter) for complex commands**—offers the best balance of speed, privacy, and intelligence across various hardware tiers.

## Research Questions

### 1. Whisper.cpp Performance & Latency
- **GPU Acceleration:** CUDA-enabled Tiny/Base models achieve near-instantaneous (10-20ms) inference for 30s audio chunks.
- **Quantization:** `q5_1` (5-bit) is the optimal balance, offering 2.5x speed gains with negligible (1-2%) accuracy loss.
- **RAM Resident Mode:** Keeping the model in RAM via a long-running daemon is critical for sub-100ms response times.
- **Scaling:** Latency scales in 30s increments due to Whisper's fixed-window architecture.
- **Detailed Asset:** [whisper_performance.md](local-whisper-streaming/whisper_performance.md)

### 2. Streaming Technical Feasibility
- **Integration:** `pywhispercpp` is the recommended Python binding due to its GIL-releasing C++ implementation and native segment callbacks.
- **VAD Integration:** **Silero VAD** is the standard for reliable, local voice activity detection to trigger transcription segments.
- **Concurrency:** A **Producer-Consumer** architecture using `multiprocessing.Process` is required to prevent audio drops during high-CPU inference.
- **Feedback:** Real-time UI updates can be achieved via `new_segment_callback` for incremental text display.
- **Detailed Asset:** [streaming_feasibility.md](local-whisper-streaming/streaming_feasibility.md)

### 3. Command Mode & Local LLM Integration
- **VRAM Contention:** Running Whisper (int8) and Llama 3.2 3B (Q4) requires ~7-9GB VRAM. CPU-offloading for Whisper is a viable alternative for lower-end GPUs.
- **Local Advantage:** Local LLMs (Llama 3.2 3B) provide ~120ms TTFT, significantly outperforming cloud APIs for short command tasks.
- **Hybrid Model:** Local STT + Cloud LLM is a robust "Privacy-First" alternative that keeps raw audio local while using cloud intelligence for reasoning.
- **Installation:** Bundled solutions (e.g., Ollama, FFmpeg) are essential to mitigate setup complexity for end-users.
- **Detailed Asset:** [command_mode_integration.md](local-whisper-streaming/command_mode_integration.md)

### 4. Architectural Impact & Roadmap
- **Daemon Refactor:** `HarpDaemon` must be re-engineered for concurrency, replacing the sequential record-transcribe-type loop with an async pipeline.
- **Config & Lifecycle:** `.harp.yaml` requires a new `local_whisper` section for model selection and automated downloading.
- **Feature Preservation:** "Clipboard Context" can be injected as an `initial_prompt` into Whisper to bias the model towards relevant jargon.
- **Testing Strategy:** Hardware-agnostic CI can be maintained by mocking `faster-whisper` and using WAV file simulations for "microphone" input.
- **Detailed Asset:** [architectural_impact.md](local-whisper-streaming/architectural_impact.md)

## Conclusions

Moving to a **local-first streaming architecture** is not only feasible but highly recommended to elevate **Harp** from a "convenient tool" to a "seamless, near-instantaneous interface." The primary challenges are **VRAM management** for simultaneous STT/LLM usage and the **architectural complexity** of a concurrent streaming pipeline. However, the benefits in privacy, latency, and user experience far outweigh these technical hurdles.

## Recommendations

1.  **Phase 1: Local Batch Integration:** Integrate `faster-whisper` as an alternative to OpenRouter for batch transcription. This provides an immediate privacy and cost win without needing a full streaming refactor.
2.  **Phase 2: Streaming Prototype:** Implement a concurrent prototype using `pywhispercpp` and Silero VAD to test real-world responsiveness and input injection timing.
3.  **Phase 3: Hybrid Default:** Set the default configuration to Local Whisper (Base/Small) + OpenRouter (Gemini 2.0 Flash) to offer the best speed and intelligence mix.
4.  **Phase 4: Local Command Mode:** Integrate **Ollama** as an optional backend for "Command Mode" for users with 8GB+ VRAM.
5.  **Follow-up Research:** Investigate **Distil-Whisper** or **Whisper-Large-v3-Turbo** for even faster inference without accuracy loss.

**Final Suggestion:** The research is complete. You can now use the `/draft` command to turn this executive report into a fully fleshed-out implementation plan or white paper for the community.
