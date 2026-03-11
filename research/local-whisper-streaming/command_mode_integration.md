# Command Mode & Local LLM Integration for Whisper

## 1. Executive Summary
Integrating a local LLM with local Whisper ("Command Mode") offers a significant leap in responsiveness and privacy for voice-controlled workflows. While resource contention (particularly VRAM) is a primary technical challenge, it can be mitigated through aggressive quantization, strategic memory management, and model selection (e.g., Llama 3.2 1B/3B). A "Hybrid" approach—local transcription paired with cloud-based reasoning—remains a highly feasible intermediate step for users with lower-end hardware.

## 2. Resource Contention: Whisper + Local LLM
Running both models simultaneously creates competition for system resources, primarily GPU VRAM.

### 2.1 The VRAM Bottleneck
- **Ollama (Llama 3.2 3B):** Requires ~2.5 GB - 3.5 GB VRAM.
- **Faster-Whisper (Large-v3):** Requires ~3.1 GB (int8) to ~5 GB (float16) VRAM.
- **Combined Impact:** On an 8GB GPU, running both comfortably is possible but leaves little "headroom" for other tasks. On a 6GB GPU, "spillover" to System RAM is likely, which can degrade LLM performance by 5x-10x.

### 2.2 Mitigation Strategies
| Strategy | Impact | Implementation |
| :--- | :--- | :--- |
| **Aggressive Quantization** | Reduces VRAM by 50%+ | Use `int8_float16` for Whisper and `Q4_K_M` for Ollama. |
| **Model Unloading** | Frees VRAM between tasks | Set `OLLAMA_KEEP_ALIVE=0` to unload the LLM after each command. |
| **Context Limiting** | Reduces VRAM/Compute | Limit LLM `num_ctx` to 2048 for short command tasks. |
| **Heterogeneous Compute** | Distributes load | Run Whisper on CPU (highly optimized) and LLM on GPU. |

## 3. Latency Analysis: Local vs. OpenRouter
For "Command" tasks (e.g., "Summarize this," "Rewrite as email"), the user's perception of speed is driven by **Time to First Token (TTFT)**.

### 3.1 Latency Comparison
| Metric | Local (Llama 3.2 3B via Ollama) | OpenRouter (GPT-4o / Claude 3.5) |
| :--- | :--- | :--- |
| **TTFT (Start Delay)** | **~100ms - 150ms** | **400ms - 800ms** |
| **Total Time (Short Cmd)** | **< 1 second** | **1.5 - 3.0 seconds** |
| **Native "Feel"** | High (Instantaneous) | Low (Noticeable network lag) |

**Key Finding:** Local LLMs are superior for short commands because they bypass the "network tax." Even if a cloud model has higher throughput, the local model finishes the entire 1-sentence rewrite before the cloud model even begins streaming tokens.

## 4. Hybrid Model: Local Whisper + API LLM
A hybrid approach uses the local device as the "ears" (Whisper) and the cloud as the "brain" (OpenRouter).

### 4.1 Feasibility & UX Impact
- **Privacy (High):** Raw audio never leaves the device. Only transcribed text is sent to the cloud, significantly reducing the data footprint and privacy risk.
- **Speed (Medium-High):** Local transcription provides immediate visual feedback (streaming text). The slight delay for the LLM response is offset by the "perfect" transcription quality.
- **Reliability:** The system requires internet for the "intelligence" part but can still perform basic local transcription/text-entry tasks offline.
- **UX Recommendation:** Use a "Local-First" fallback. Use a 1B local model for simple commands (e.g., "delete that," "uppercase") and route complex requests to OpenRouter.

## 5. Installation & Hardware Requirements
The transition to a local-first setup significantly increases the "entry barrier" for the average user.

### 5.1 Hardware Requirements (Tiers)
| Tier | Hardware | Capability |
| :--- | :--- | :--- |
| **Minimum** | 8GB RAM, modern 6-core CPU | Whisper (Base) + Llama 3.2 1B (CPU only). |
| **Recommended** | 16GB RAM, 8GB VRAM (NVIDIA) | Whisper (Medium) + Llama 3.2 3B (GPU). |
| **Pro / Mac** | 24GB+ Unified Memory (M2/M3) | Whisper (Large-v3) + Llama 3.1 8B (Shared). |

### 5.2 Installation Complexity
- **Ollama:** Extremely simple (one-click installer, zero dependencies).
- **Whisper:** High complexity. Requires Python, FFmpeg, and often manual CUDA driver configuration.
- **Solution:** To maintain a good UX, the application should either bundle a pre-compiled `whisper.cpp` binary or rely on a "Portable AI" solution like **AnythingLLM** or **Pinokio**-style installers that manage dependencies automatically.

## 6. Conclusions & Recommendations
1. **Prioritize Llama 3.2 3B:** It is the current "gold standard" for local commands, offering the best balance of reasoning and speed.
2. **Implement "Eager Unloading":** To avoid VRAM contention, the application should signal Ollama to unload models when the "Command Mode" session ends.
3. **Hybrid as Default:** Start with Local Whisper + OpenRouter for the best "out of the box" experience, allowing power users to toggle "Full Local" if they have the hardware.
4. **Bundle FFmpeg:** The single biggest point of failure for local Whisper is the missing FFmpeg dependency; this must be handled by the installer.
