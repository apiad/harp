# Interactive Transcription Strategies: Non-Streaming Architectures

## Executive Summary
This report analyzes non-streaming architectures for real-time transcription to replace the current "backspace-everything" strategy in the `harp` project. Our research identifies that a **Cloud-Hybrid** approach—combining local Voice Activity Detection (VAD) with high-efficiency multimodal APIs like **Gemini 1.5 Flash**—is the most robust, low-latency, and cost-effective solution. 

Key insights include:
- **Replacing Backspaces with HUDs:** Direct typing into applications is prone to "input fighting" and is too slow for large corrections. A floating HUD for "interim" text, coupled with a "minimal-diff" typing strategy for "committed" text, provides a superior UX.
- **VAD-Driven Chunking:** Local VAD (Silero) is essential to reduce API costs and improve response times by creating natural segment boundaries.
- **Delta Prompting:** Standard APIs can simulate streaming through 0.5s–1.0s overlaps and specialized prompting that instructs the model to only output "new" text based on previous context.
- **Architecture Efficiency:** Gemini 1.5 Flash is 40x cheaper and up to 2x faster than OpenAI's Whisper API for short-chunk interactive use cases.

## Research Questions

### 1. Analysis of Current Implementation Hurdles
Current interactive transcription in `harp` uses a "backspace-everything" strategy, which is inefficient for real-time feedback. Detailed research is available in [q1_implementation_hurdles.md](./interactive-transcription/q1_implementation_hurdles.md).

**Key Findings:**
- **Keyboard Emulation Bottlenecks:** `evdev/uinput` speed is limited by the Linux kernel ring buffer. Backspacing more than 50 characters causes a visible "deletion crawl" (over 500ms at safe speeds) and risks missing events if pushed too fast.
- **Race Conditions:** User input can interleave with daemon-sent backspaces, leading to "input fighting" where the daemon accidentally deletes characters the user is currently typing.
- **Visual Flicker:** Standard STT models (Whisper/Gemini) often refine the beginning of a sentence as more context arrives. Without stability filtering, this causes the entire text to flicker as it is deleted and re-typed.
- **Overhead:** Re-transcribing the entire accumulated buffer every 2 seconds increases API latency and cost as the recording grows.

#### Detailed Assets:
- [Analysis of Implementation Hurdles](./interactive-transcription/q1_implementation_hurdles.md)

### 2. Stateless "Pseudo-Streaming" via Standard APIs
Standard APIs can be used to simulate streaming by using overlapping chunks and specialized prompting to obtain "deltas". Detailed research is available in [q2_pseudo_streaming_apis.md](./interactive-transcription/q2_pseudo_streaming_apis.md).

**Key Findings:**
- **Overlap Strategy:** 5-10s chunks with 0.5-2.0s overlap are optimal for maintaining context. "Stitching" can be handled via fuzzy matching or by using a low-latency model like Gemini 1.5 Flash to resolve boundaries.
- **Whisper Context:** The `prompt` parameter in OpenAI's `whisper-1` (V2/V3) is limited to 224 tokens and primarily maintains style/vocabulary rather than strict instruction-following.
- **Gemini Multimodal Strengths:** Gemini 1.5 Flash is highly effective for "delta" transcription. By passing the previous context (text) along with the current audio chunk, it can be prompted to only output the newly heard text.
- **Performance:** GPT-4o-realtime (where available) is the leader in latency, but Gemini 1.5 Flash offers the best balance of context window size and cost for interactive use.
- **Forcing Delta Outputs:** Techniques like "anchor prompting" (referencing the last few words) and setting low temperature (0.0) are essential for consistent incremental outputs.

#### Detailed Assets:
- [Pseudo-Streaming via Standard APIs](./interactive-transcription/q2_pseudo_streaming_apis.md)

### 3. Chunking Strategies & Contextual Continuity
Effective chunking and stitching are critical for accurate, low-latency transcription. Detailed research is available in [q3_chunking_stitching.md](./interactive-transcription/q3_chunking_stitching.md).

**Key Findings:**
- **Optimal Balance:** 0.7s to 1.2s chunks with a 15-20% overlap (200ms to 500ms) provide the best compromise between responsiveness and word-boundary safety.
- **VAD Implementation:** Silero VAD is highly recommended. Using its `VADIterator` with a 400ms `min_silence_duration_ms` allows for natural chunking during speech pauses.
- **Stitching Algorithms:**
    - **Local Agreement (LA-n):** Only "commits" text that has appeared and remained stable across multiple overlapping windows, drastically reducing flickering.
    - **Fuzzy Overlap-Matching:** Using Levenshtein distance to find the optimal merge point between overlapping chunks.
- **Hybrid Loop Logic:** A combination of **VAD-driven** triggers (on silence) and **Time-driven** fallbacks (every 5 seconds) ensures the system remains responsive even during continuous speech.
- **Lookback Context:** Sending 2-3 seconds of previous audio context with each new chunk significantly improves the accuracy of the current transcription by providing acoustic and linguistic grounding.

#### Detailed Assets:
- [Chunking and Stitching Strategies](./interactive-transcription/q3_chunking_stitching.md)

### 4. "Smart" Text Refinement & UI Feedback
Intelligent feedback mechanisms are necessary to minimize disruptive backspacing and ensure a smooth user experience. Detailed research is available in [q4_smart_refinement.md](./interactive-transcription/q4_smart_refinement.md).

**Key Findings:**
- **LLM Stabilizers:** Using a low-latency model like Llama 3 (on Groq) or Gemini 1.5 Flash as a "semantic filter" can help decide when a transcribed segment is "final" vs. "provisional". This avoids typing half-finished words.
- **Ghost Text Pattern:** Implementing a "Committed vs. Interim" buffer. Only committed text is typed into the application, while interim text is shown in a small, floating HUD overlay. This eliminates backspacing in the target app.
- **Retroactive Correction UX:** A "Depth Threshold" approach is recommended: only perform silent corrections on the last 1-3 words. For corrections further back, it is better to leave them or mark them for manual review rather than triggering a large, jarring backspace sequence.
- **Confidence Heuristics:** Whisper's `logprobs` and `no_speech_prob` can be used to gauge transcription reliability. High-confidence segments are committed immediately; low-confidence ones wait for a second pass (Local Agreement).
- **Preventing Input Fighting:** Detecting user keyboard activity via global listeners (like `pynput`) can pause the daemon's automated typing to prevent interleaving characters. A 500ms-1s idle timeout before resuming is a common best practice.

#### Detailed Assets:
- [Smart Refinement and UI Feedback Strategies](./interactive-transcription/q4_smart_refinement.md)

### 5. Architecture Trade-offs: Latency, Cost, and Accuracy
Different architectures provide different balances of cost, speed, and accuracy. Detailed research is available in [q5_architecture_tradeoffs.md](./interactive-transcription/q5_architecture_tradeoffs.md).

**Key Findings:**
- **Lowest Latency:** Google Gemini 1.5 Flash (direct) currently provides the fastest Round Trip Time (RTT) for short audio payloads (400ms – 800ms) compared to OpenAI's Whisper-1 (~1.2s – 2.0s).
- **Lowest Cost:** Gemini 1.5 Flash is significantly more cost-effective (~$0.0086 per hour of active speaking in 1.5s chunks) than OpenAI Whisper-1 (~$0.36 per hour).
- **Mandatory Local VAD:** Implementing a local Voice Activity Detection (VAD) layer (like Silero VAD) is essential. It reduces API costs by up to 60% by filtering out silence and reduces perceived latency by up to 800ms by eliminating the need for the model to "wait" for silence.
- **Local vs. Cloud:** While local-first solutions (e.g., `faster-whisper` on NVIDIA) offer zero network latency, they require dedicated hardware. A **Cloud-Hybrid** approach (Local VAD + Gemini 1.5 Flash API) offers the best overall performance and flexibility for a wide range of devices.
- **Protocol Optimization:** Preferring HTTP/2 or gRPC for API communication minimizes the overhead of frequent small requests compared to standard HTTP/1.1.

#### Detailed Assets:
- [Architecture Trade-offs and Benchmarks](./interactive-transcription/q5_architecture_tradeoffs.md)

## Conclusions
1. **Current Limitations are Structural:** The "backspace-and-retype" approach is inherently flawed due to `uinput` speed limits and inevitable race conditions with user input. It should be relegated to small "committed" segments only.
2. **Standard APIs are Viable:** We do not need a stateful WebSocket engine. Stateless REST APIs with 500ms–1s chunks and acoustic context (lookback) are sufficient for near-real-time feedback.
3. **Gemini 1.5 Flash is the Optimal Backend:** Its native support for audio tokens, massive context window, and low cost make it superior to Whisper for high-frequency interactive tasks.
4. **Local VAD is Mandatory:** A background daemon cannot rely on a cloud API for silence detection without incurring massive costs and latency penalties.

## Recommendations
1. **Implement Local VAD:** Integrate `silero-vad` to manage audio chunking. Stop re-sending the entire buffer; instead, send 5-second "rolling" chunks with 1-second overlaps.
2. **Adopt a Dual-Buffer UX:**
    - **Committed Buffer:** Text that has been confirmed by a "Local Agreement" (multiple passes). Type this into the app using a **minimal-diff** (LCP) algorithm.
    - **Interim Buffer:** Unstable "ghost text" displayed in a lightweight floating HUD (e.g., via `GTK` or a simple Wayland layer). Never type this into the active window.
3. **Switch to Gemini 1.5 Flash:** Transition the default interactive backend to Gemini 1.5 Flash. Use system instructions to enforce "delta-only" output by providing the last 200 characters of committed text as context.
4. **Safety Mechanisms:** Implement a global keyboard listener to pause automated typing whenever physical keypresses are detected. Add an adjustable "Safe Typing Speed" to avoid overflowing the kernel input buffer.
5. **Phase Out Global Buffer Peeking:** Transition from peeking at the entire `audio_buffer` to a sliding window queue of audio segments to reduce memory and network overhead.
