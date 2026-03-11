# Transcription Prompt Optimization for OpenRouter Multimodal Models

This document outlines the impact of prompt engineering, system messages, and OpenRouter-specific parameters on transcription latency (TTFT and total time) for multimodal models.

## 1. Impact of Prompt Length and Complexity on Latency

In multimodal LLMs (like Gemini 2.0 Flash Lite, GPT-4o-audio, or Voxtral), transcription is handled as a "chat completion" task with audio input.

- **TTFT (Time to First Token):** This is the primary metric affected by prompt length. The model must "prefill" (process) all input tokens—including the system message, user text, and audio tokens—before it can generate the first word of transcription. 
- **Linear Scaling:** TTFT increases linearly with the number of tokens in the `system_message` or `user` text. For every 1,000 tokens of prompt context, expect a baseline increase in TTFT (typically ~10-50ms depending on the model/provider).
- **Complexity vs. Length:** While token count is the main driver, extremely complex logic (e.g., "Transcribe only the parts about X, then translate to Y, then format as a table") can marginally increase the model's internal processing time before generation starts.
- **Initial Prompt (Whisper-style):** Unlike dedicated Whisper endpoints, OpenRouter's multimodal chat models do not have a separate `initial_prompt` parameter. The "prompt" is simply part of the message history.

## 2. Model Efficiency Comparison

| Model | Median TTFT (Audio) | Best For |
| :--- | :--- | :--- |
| **Voxtral Small 24B** | **~140ms - 500ms** | Ultra-low latency, audio-native reasoning, Mistral-based logic. |
| **Gemini 2.5/3.1 Flash Lite** | **~380ms** | Extreme speed, massive context (1M+ tokens). |
| **Gemini 2.0 Flash Lite** | **~1,100ms** | General-purpose multimodal tasks, high accuracy, robust instruction following. |
| **GPT-4o-audio-mini** | **~600ms - 900ms** | High-quality OpenAI ecosystem, good balance of speed/accuracy. |

**Recommendation:** For raw transcription speed where latency is the bottleneck, **Voxtral** or **Gemini Flash Lite (Preview)** models are superior to the standard "Pro" or "Large" variants.

## 3. Dynamic Context Injection Strategies

Injecting dynamic context (clipboard, window titles, active application name) can improve transcription accuracy but risks increasing latency if not handled correctly.

### Best Practices:
1. **Append, Don't Prepend:** Always place dynamic context at the **end** of the `messages` array (or at the end of the `user` message text).
2. **Protect the Prefix:** OpenRouter and its providers (like Google, Anthropic, DeepSeek) use **Prompt Caching** based on prefix matching. If you change the beginning of the prompt (e.g., by adding a timestamp or window title at the top), you invalidate the cache for the *entire* prompt.
3. **Use Explicit Caching (if supported):** Some models allow explicit cache breakpoints. However, for most, keeping the `system_message` static and placing dynamic content at the end is the most efficient way to leverage implicit caching, reducing TTFT by **13% to 31%**.

**Example Structure:**
```json
{
  "messages": [
    { "role": "system", "content": "Transcribe accurately. [STAY CACHED]" },
    { "role": "user", "content": [
      { "type": "input_audio", "input_audio": { "data": "...", "format": "wav" } },
      { "type": "text", "text": "Context: Active window is 'Slack'. [DYNAMIC]" }
    ]}
  ]
}
```

## 4. OpenRouter-Specific Latency Parameters

OpenRouter provides several `provider` parameters to optimize performance:

- **`provider.quantizations`**: 
  - Using `["int4"]` or `["int8"]` can route to faster, lower-precision models.
  - Using `["fp16"]` ensures higher accuracy but may route to slower hardware.
- **`provider.sticky: true`**:
  - Crucial for Prompt Caching. It ensures your request returns to the same provider that already has your system message in its cache.
- **`provider.order` / `provider.only`**:
  - Manually specify low-latency providers like `DeepInfra`, `Mistral`, or `Google` to bypass slower fallbacks.
- **`stream: true`**:
  - While it doesn't reduce TTFT, it significantly reduces *perceived* latency by showing the transcription as it's being generated.

## 5. Prompt-Heavy vs. Prompt-Light Latency

| Feature | Prompt-Light (Minimal) | Prompt-Heavy (Complex Context) |
| :--- | :--- | :--- |
| **Instruction Size** | < 50 tokens | 500+ tokens |
| **TTFT Impact** | Baseline (~400-800ms) | +50ms to +200ms overhead |
| **Cache Hit Probability** | High (static) | Low (if dynamic context is prepended) |
| **Accuracy** | Standard | Higher (better handling of jargon/names) |

**Conclusion:** For "real-time" feeling, use a **Prompt-Light** approach with a static system message and a high-performance model like **Voxtral**. Use dynamic context sparingly and always append it to the end of the request.
