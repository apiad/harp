# Robust Strategy for Audio Chunking and Transcript Stitching

This document outlines a robust strategy for implementing interactive (real-time) transcription, focusing on the balance between latency, accuracy, and seamless text integration.

---

## 1. Optimal Balance: Duration, Overlap, and Latency

For a responsive desktop application, the configuration must balance the "human" perception of real-time interaction (~500ms) with the acoustic context needed for ASR accuracy.

| Parameter | Recommended Value | Rationale |
| :--- | :--- | :--- |
| **Audio Frame (Network)** | 40ms - 100ms | Small enough for fluid UI updates, large enough to minimize packet overhead. |
| **Processing Chunk** | 0.7s - 1.2s | Optimal window for models (like Whisper) to resolve homophones and context. |
| **Lookback Overlap** | 200ms - 500ms | Prevents word clipping at boundaries. Generally ~15-20% of chunk length. |
| **Total Pipeline Latency**| < 500ms | The "Interactive Threshold" for natural-feeling conversation. |

### The "Stable Partial" Strategy
Instead of waiting for a "Final" result (which takes >1s), the app should emit **Interim/Partial results** every 100-200ms. These are unstable but provide immediate visual feedback. Once the VAD detects silence or the chunk is processed, a "Final" result replaces the unstable partials.

---

## 2. Implementing Voice Activity Detection (VAD)

Using **Silero VAD** is recommended due to its high accuracy and low overhead. To avoid cutting words, use the stateful `VADIterator`.

### Practical Implementation (Python)
```python
import torch
from silero_vad import load_silero_vad, VADIterator

# Configuration
SAMPLING_RATE = 16000
model = load_silero_vad()
vad_iterator = VADIterator(
    model, 
    threshold=0.5,              # Sensitivity
    sampling_rate=SAMPLING_RATE,
    min_silence_duration_ms=400, # Wait 400ms before ending speech (prevents mid-word cuts)
    speech_pad_ms=50            # Add padding to ensure the very start/end aren't clipped
)

def process_chunk(audio_float32_tensor):
    # Returns 'start' or 'end' dict when a boundary is crossed
    speech_dict = vad_iterator(audio_float32_tensor, return_seconds=True)
    return speech_dict
```

**Key for Robustness:** `min_silence_duration_ms` should be tuned (300ms-600ms). Too low, and natural pauses in a sentence will trigger a "Final" transcription, breaking the sentence apart.

---

## 3. Comparative Analysis of Stitching Algorithms

Stitching is required when the end of Chunk A and the start of Chunk B contain overlapping audio/text.

| Algorithm | Mechanism | Best For | Pros/Cons |
| :--- | :--- | :--- | :--- |
| **LCS (Longest Common Subsequence)** | Finds exact token matches in order. | Clean audio, low latency. | **Pro:** Verbatim. **Con:** Breaks on minor ASR variations (e.g., "U.S.A" vs "USA"). |
| **Overlap-Matching (Fuzzy)** | Uses Levenshtein/Smith-Waterman distance on the overlap region. | Noisy environments, varied ASR output. | **Pro:** Handles typos/noise. **Con:** Computationally more expensive (use `RapidFuzz`). |
| **LLM-Based Stitching** | Feeds overlapping segments to an LLM to merge. | Complex dialogue, resolving hallucinations. | **Pro:** Highest accuracy, fixes grammar. **Con:** High latency, API cost. |
| **Local Agreement (LA-n)** | Commits only the prefix that matches across $n$ consecutive windows. | Streaming (Whisper). | **Pro:** Standard for streaming; prevents "flicker". **Con:** Adds latency proportional to $n$. |

### Recommendation: The "Local Agreement" Approach
For interactive apps, use **Local Agreement (n=2)**. Compare the current transcript with the previous one. Only display the prefix where both agree. This naturally handles the "stitching" by only advancing the "confirmed" text cursor.

---

## 4. Handling 'Lookback' Context

A "Lookback" window provides the ASR model with the acoustic and linguistic context of what was just said, which is critical for the "Local Agreement" algorithm to find a match.

- **Acoustic Lookback:** Send **2.0s - 3.0s** of previous audio along with the new chunk. This ensures the model "re-hears" the last few words of the previous chunk, allowing for a clean merge point.
- **Linguistic Context (`initial_prompt`):** For Whisper-like models, pass the last **200 characters** of the *already confirmed* text as the `initial_prompt`. This prevents the model from changing its spelling style or language mid-stream.

---

## 5. Practical Logic: VAD-driven vs. Time-driven

An async loop should combine both triggers to ensure responsiveness even during long monologues.

### Async Loop Logic (Pseudo-code)
```python
class TranscriptionManager:
    def __init__(self):
        self.buffer = []
        self.is_speaking = False
        self.MAX_CHUNK_TIME = 5.0 # Max 5s before forcing transcription
        self.last_flush = time.time()

    async def main_loop(self):
        async for frame in audio_source:
            self.buffer.append(frame)
            is_speech = await silero_vad(frame)
            
            # Condition 1: VAD-driven (Speaker paused)
            if self.is_speaking and not is_speech:
                await self.flush_and_transcribe("VAD_SILENCE")
                self.is_speaking = False
            
            # Condition 2: Time-driven (Safety fallback for long speech)
            elif time.time() - self.last_flush > self.MAX_CHUNK_TIME:
                await self.flush_and_transcribe("MAX_DURATION")
            
            if is_speech:
                self.is_speaking = True

    async def flush_and_transcribe(self, trigger):
        audio_to_send = b"".join(self.buffer)
        # 1. Transcribe (Chunk + 2s Lookback)
        # 2. Apply Local Agreement with previous result
        # 3. Update UI
        # 4. Clear buffer but keep 'Lookback' audio for the next round
        self.buffer = self.buffer[-LOOKBACK_FRAMES:] 
        self.last_flush = time.time()
```

### Summary of Robust Logic:
1.  **VAD** handles natural breaks (sentences).
2.  **Time-limit** handles long utterances (preventing huge latency).
3.  **Local Agreement** ensures the UI doesn't "jump" or flicker.
4.  **Audio Lookback** provides the "glue" for the stitching logic to work.
