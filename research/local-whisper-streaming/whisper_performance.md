# Whisper.cpp Performance & Latency Research Report

This report provides a detailed analysis of `whisper.cpp` performance, latency, and resource requirements on Linux systems, comparing local inference with Cloud API alternatives.

## 1. Latency Benchmarks (CPU vs. GPU)

Whisper.cpp performance on Linux is highly dependent on the hardware backend (AVX2/AVX-512 for CPUs, CUDA/Vulkan for GPUs). The primary bottleneck is the **Encoder Latency**, which is the time taken to process one 30-second audio chunk.

### 30s Audio Chunk Latency (Typical Desktop)
The following benchmarks represent high-end consumer hardware (e.g., Ryzen 7/9, RTX 3060/4060).

| Model | CPU Encoder Latency | GPU Encoder Latency (CUDA) | Real-Time Factor (RTF) |
| :--- | :--- | :--- | :--- |
| **Tiny** | ~400 – 450 ms | ~8 – 12 ms | 20x – 50x |
| **Base** | ~800 – 900 ms | ~15 – 20 ms | 15x – 30x |
| **Small** | ~2,500 – 3,000 ms | ~50 – 70 ms | 4x – 10x |

*   **Real-Time Factor (RTF):** Calculated as `(Audio Duration) / (Processing Time)`. An RTF of 10x means 60 seconds of audio is processed in 6 seconds.
*   **GPU Advantage:** CUDA-enabled GPUs offer a 10x–50x speedup over CPUs, making transcription effectively "instantaneous" for most interactive use cases.

## 2. Quantization: Accuracy vs. Speed

Quantization is the primary method for optimizing `whisper.cpp` for consumer hardware. It reduces the precision of model weights (e.g., from 16-bit to 4-bit or 5-bit).

### Comparison of Quantization Methods

| Quantization | Size (Large-v3) | Accuracy (WER) | Speed Gain (vs f16) | Recommendation |
| :--- | :--- | :--- | :--- | :--- |
| **f16 (Original)** | ~3.1 GB | Baseline | 1.0x | Reference |
| **q5_1 (5-bit)** | ~1.1 GB | -1% to -2% | ~2.5x | **The "Sweet Spot"** |
| **q4_0 (4-bit)** | ~890 MB | -3% to -5% | ~3.0x | **Max Speed** |

*   **Accuracy (Word Error Rate):** 5-bit (`q5_1`) models are widely considered the gold standard, offering accuracy nearly indistinguishable from full-precision models. 4-bit (`q4_0`) models show a more noticeable drop in accuracy, particularly with background noise or technical accents.
*   **Performance:** 4-bit models are roughly **20-30% faster** than 5-bit models on most CPUs. On GPUs, the speed difference is often negligible due to memory bandwidth being the primary limiter.

## 3. Memory Footprint & Cold Start

### Memory Usage
`whisper.cpp` uses a "zero-allocation" strategy. Once the model is loaded, memory usage remains flat.

| Model Size | Disk Space | RAM (Approx.) | Cloud API Local RAM |
| :--- | :--- | :--- | :--- |
| **Tiny** | ~75 MB | ~275 MB | ~10–50 MB |
| **Base** | ~145 MB | ~400 MB | ~10–50 MB |
| **Small** | ~480 MB | ~850 MB | ~10–50 MB |
| **Large (v3)** | ~3.0 GB | ~4.0 GB | ~10–50 MB |

### Cold Start Comparison
"Cold start" is the time from the execution command to the first word of transcription.

*   **Local (whisper.cpp):**
    *   **Model Loading:** ~150ms (Base) to ~1s (Large) on modern SSDs.
    *   **Total Start Time:** **< 1.5 seconds**.
    *   **Server Mode:** If running in server mode, the model stays resident in RAM, reducing "cold start" to **sub-100ms** response times.
*   **Cloud API (e.g., OpenAI):**
    *   **Overhead:** Includes DNS lookup, TLS handshake, and audio file upload.
    *   **Total Start Time:** **2–10+ seconds**, heavily dependent on internet upload speed.

## 4. Latency Scaling with Audio Duration

Whisper operates on a **fixed 30-second window**. This has unique implications for latency scaling.

### Scaling Behavior (2s vs. 30s)

*   **The 30s Constant:** Regardless of whether the audio is 2 seconds or 29 seconds, the model pads the input to 30 seconds. The **Encoder pass** (the most expensive part) takes the same amount of time for both.
*   **Step-Function Scaling:** Latency does not scale linearly with every second; it scales in 30-second steps.
    *   **0s - 30s:** 1x base latency (single encoder pass).
    *   **31s - 60s:** 2x base latency (two encoder passes).
*   **Minor Linear Factor:** The **Decoder pass** (generating text tokens) *does* scale with the number of spoken words. A 2s clip will have slightly faster decoding than a 30s clip, but the difference is usually negligible compared to the fixed encoder time.

### Latency Summary Table

| Audio Duration | Processing Mode | Perceived Latency |
| :--- | :--- | :--- |
| **2s (Command)** | Single 30s window | ~0.5s (CPU) / ~0.02s (GPU) |
| **30s (Dictation)** | Single 30s window | ~0.6s (CPU) / ~0.03s (GPU) |
| **45s (Long)** | Two 30s windows | ~1.1s (CPU) / ~0.06s (GPU) |

## Key Findings for Implementation

1.  **Prefer `q5_1`:** For the best balance of speed and accuracy, `q5_1` is the recommended quantization.
2.  **GPU is Mandatory for "Instant" Feel:** While CPUs are usable for `tiny` and `base` models, a GPU is required for the low-latency response (~20-50ms) expected in interactive voice applications.
3.  **Use Server Mode:** To eliminate "cold start" latency during active sessions, keep the model resident in RAM via a background daemon or server.
4.  **Audio Chunking Strategy:** Since the model processes in 30s chunks, there is no latency penalty for sending 25s of audio vs. 5s of audio. However, sending >30s will double the processing time.
