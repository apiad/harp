# Stateless Pseudo-Streaming Transcription Research

This document outlines strategies for implementing near-real-time transcription using non-streaming APIs from OpenAI, Google (Gemini), and OpenRouter.

---

## 1. Overlapping Audio Chunk Strategy
To achieve "pseudo-streaming" with stateless APIs, audio is captured in small chunks and sent to the endpoint. Cutting audio at arbitrary boundaries often splits words or phonemes, leading to transcription errors at the edges.

### Chunk Parameters
- **Chunk Duration ($T$):** Typically 5–10 seconds. Shorter chunks (2–3s) reduce latency but increase API costs and overhead.
- **Overlap ($O$):** 0.5–2.0 seconds. Prepending the end of the previous chunk to the start of the current chunk ensures that any word cut off at the boundary is captured fully in the next request.

### Stitching Techniques
- **Deterministic (Fuzzy Matching):** Use algorithms like **Levenshtein Distance** or **Smith-Waterman** to find the overlap between the suffix of the previous transcript and the prefix of the current one.
- **LLM-based Stitching:** Pass both the previous "unconfirmed" text and the new transcription to a fast LLM (like Gemini 1.5 Flash) with the prompt: *"Merge these overlapping transcripts into a single seamless stream. Output only the new, non-redundant text."*
- **VAD-Gated Chunking:** Instead of fixed-time cuts, use a local **Voice Activity Detector (VAD)** (e.g., Silero) to wait for a short silence (e.g., 200ms) before cutting the chunk, minimizing split words.

---

## 2. OpenAI Whisper `prompt` Parameter
The `whisper-1` API includes a `prompt` parameter specifically for maintaining context across segments.

### Capabilities
- **Style & Vocabulary:** It forces the model to maintain consistent spelling (e.g., technical terms, proper names) and formatting (casing, punctuation).
- **Continuity:** By passing the last 224 tokens of the previous transcript, Whisper "sees" where it left off, reducing boundary artifacts.

### Critical Constraints
- **224 Token Limit:** Only the **final 224 tokens** of the prompt are considered. Longer prompts are silently truncated from the beginning.
- **Mimicry vs. Instructions:** Whisper does **not** follow instructions in the prompt (e.g., "Don't use periods"). It mimics the *style* of the provided text. To get a specific format, the prompt itself must be in that format.
- **Heuristic Nature:** The model treats the prompt as a hint, prioritizing the actual audio signal if there is a conflict.

---

## 3. Gemini 1.5 Multimodal Context & "Delta" Output
Gemini 1.5 Pro and Flash are natively multimodal, meaning they "hear" audio tokens directly alongside text tokens.

### Multimodal Input Pattern
Send a request containing:
1. **System Instruction:** "You are a real-time transcriber. I will provide the transcript so far and a new audio chunk."
2. **Text Context:** The last few sentences of the confirmed transcript.
3. **Audio Content:** The current (possibly overlapping) audio chunk.

### The 'Delta' Strategy
Unlike standard ASR which returns the full segment transcript, Gemini can be prompted to **output only the new text**.
- **Prompt:** *"Based on the previous transcript provided, transcribe the new audio and output only the text that follows the context. Do not repeat the context."*

### Context Caching
For long sessions, Gemini allows caching the previous audio/text context on the server, significantly reducing the tokens (and cost) sent in subsequent "delta" requests.

---

## 4. Performance Comparison: STT vs. Audio-LLMs

| Feature | OpenAI Whisper (v3) | GPT-4o (Audio) | Gemini 1.5 Flash |
| :--- | :--- | :--- | :--- |
| **Primary Strength** | Robustness & Cost | Accuracy & Tone | Context Window (1M+) |
| **Latency** | 500ms - 2s (API) | **Sub-300ms** (Realtime API) | 400ms - 1s |
| **Context Awareness** | Limited (224 tokens) | High (128k tokens) | **Extreme (1M+ tokens)** |
| **Hallucinations** | Low (mostly repeats) | Moderate (may "complete") | Low-Moderate |
| **Output Type** | Text only | Text + Audio (TTS) | Text only |
| **Ideal Use Case** | Bulk transcription / Batch | Voice Assistants / Live | Long meetings / Analysis |

*Note: Whisper is extremely fast on providers like Groq (sub-200ms for short chunks), but lacks the conversational context of GPT-4o or Gemini.*

---

## 5. Techniques to Force 'Delta' Output
To prevent the model from repeating text or adding preambles, use the following techniques:

1. **JSON Mode:** Force the output into a JSON object `{"new_text": "..."}`. This prevents "Here is the transcript:" preambles.
2. **Anchor Prompting:** Provide the last 3 words of the previous transcript and instruct: *"Continue transcribing immediately after the phrase '[Last 3 words]'. Do not include the phrase itself."*
3. **Few-Shot Examples:** Provide 2-3 examples of `[Context] + [Audio] -> [Delta]` in the system prompt to establish the pattern.
4. **Temperature 0:** Always set `temperature: 0.0` for transcription to ensure deterministic output and reduce "creative" hallucinations.

---

## 6. OpenRouter Audio Transcription
OpenRouter facilitates access to `gpt-4o-audio-preview` and `gemini-1.5-flash` via their standard Chat Completions API.
- **Format:** Audio is typically sent as a `base64` string within the `content` array using the `input_audio` type.
- **Unified API:** This allows switching between OpenAI and Google backends with minimal code changes, though the `input_audio` parameter names may vary slightly between underlying providers.
- **Pass-through Pricing:** You pay the provider's rate per million tokens, where 1M audio tokens roughly equal 1-2 hours of audio.

---
### Implementation Summary for Harp
For a robust pseudo-streaming implementation:
1. **Client:** Capture 5s chunks with 1s overlap.
2. **API:** Use **Gemini 1.5 Flash** for its balance of speed and massive context.
3. **Logic:** Use the `system_instruction` to define the "transcribe only new text" behavior.
4. **Fallback:** If the LLM repeats text, use a client-side **Levenshtein fuzzy match** to find the stitch point and deduplicate the stream.
