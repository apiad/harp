# Performance and Reliability Analysis: 'Backspace-and-Retype' Strategies

This document analyzes the technical challenges and performance implications of using keyboard emulation for real-time transcription on Linux (Wayland/X11), specifically focusing on the 'backspace-and-retype' mechanism used to handle streaming updates from models like Whisper or Gemini.

## 1. Keyboard Emulation Speed (evdev/uinput)

When using `uinput` or `evdev` to emulate keyboard input, the system's performance is bound by several factors that impact the user experience (UX), especially when dealing with large deletions (>50 characters).

### Technical Bottlenecks
*   **Kernel Ring Buffer:** The Linux kernel maintains a buffer for `evdev` events (typically 64–128 events). Sending a burst of 50 backspaces + 50 characters (100 events) in a single loop without synchronization can trigger a `SYN_DROPPED` event, causing the target application to lose synchronization and miss characters.
*   **Application Polling Rates:** Most GUI applications and terminal emulators process input at their frame rate (e.g., 60Hz or 144Hz). If events are sent faster than the application's event loop can consume them (~16.6ms per frame), the application may lag or drop inputs.
*   **Inter-Key Delay:** To ensure reliability across different environments (e.g., a slow VM vs. a native terminal), a small delay (1–10ms) is often introduced between key presses.

### UX Impact (>50 Characters)
*   **Visual "Deletion Crawl":** At a safe speed of 10ms per backspace, deleting 50 characters takes **500ms**. This creates a visible "rewind" effect where the user sees the text disappearing character by character.
*   **System Latency:** High-frequency event injection can cause micro-stutters in the UI if the compositor (Wayland) or X11 server is under heavy load.
*   **Reliability vs. Speed:** Reducing the delay to 1ms makes the deletion nearly instant (50ms) but significantly increases the risk of the target application "skipping" backspaces, leading to "ghost text" (leftover characters from the previous version).

## 2. 'Backspace-Everything' vs. 'Minimal-Diff'

Current `harp` logic uses a "backspace-everything" approach. Below is a comparison with the more advanced "minimal-diff" strategy.

### Backspace-Everything (Current)
*   **Logic:** Every time the transcription model provides a new partial result, the daemon sends `N` backspaces (where `N` is the length of the previous buffer) and types the entire new string.
*   **Pros:** Extremely simple to implement; no state comparison needed.
*   **Cons:**
    *   **High Overhead:** If only the last character of a 100-character sentence changes, it performs 100 deletions and 100 insertions.
    *   **Maximum Flicker:** The entire text block disappears and reappears constantly, which is visually exhausting for the user.
    *   **State Destruction:** Destroys word-wrap, cursor positions, and potentially triggers auto-correct/auto-complete logic repeatedly.

### Minimal-Diff (Recommended)
*   **Logic:** The daemon finds the **Longest Common Prefix (LCP)** between the `current_buffer` and the `new_partial`. It only backspaces the differing suffix and types the new suffix.
*   **Pros:**
    *   **Efficiency:** If the model adds one word, only that word is typed. If the model changes the last word, only that word is backspaced and replaced.
    *   **Reduced Flicker:** The beginning of the sentence remains stable.
    *   **Lower Collision Risk:** Fewer events mean a smaller window for "input fighting" with the user.
*   **Example:**
    *   Current: "The quick brown fox"
    *   New: "The quick brown dog"
    *   **Minimal-Diff:** Backspace 3 chars ("fox"), Type 3 chars ("dog").
    *   **Backspace-Everything:** Backspace 19 chars, Type 19 chars.

## 3. Terminal Pollution and Input Fighting

"Input fighting" occurs when the background daemon and the human user attempt to type into the same active window simultaneously.

### The Mechanism of Failure
1.  **Non-Atomicity:** Keyboard emulation is not atomic. A "replace text" operation is actually a sequence: `[BS, BS, BS, T, H, E]`.
2.  **Race Conditions:** If the user types 'A' while the daemon is sending backspaces, the sequence at the OS level might become `[BS, BS, A, BS, T, H, E]`.
3.  **Result:**
    *   **The user's 'A' is deleted** by the daemon's third backspace, which was intended for a different character.
    *   The final text becomes "THE", but the user expects "A THE" or "THE A".
    *   **Terminal Pollution:** In a terminal, if the backspace count gets out of sync with the actual character count (e.g., due to the user typing or the daemon missing an event), the cursor may move past the prompt or leave "garbage" characters on the screen that are difficult to clear without a `Ctrl+C` or `reset`.

### Mitigation Strategies
*   **Input Grabbing:** (Difficult on Wayland) Attempting to "grab" the keyboard to block user input during the millisecond-long retype window.
*   **User-Typing Detection:** If the daemon detects a physical key-down event from the user, it should immediately abort the current "backspace-and-retype" cycle and resync.

## 4. The 'Flicker' Effect in Refinement

Streaming STT models (Whisper, Gemini) use "look-ahead" or beam search algorithms. As more audio data is processed, the model often gains higher confidence and "refines" previous words.

### Causes of Flicker
*   **Correction Shifting:** The model might change "I saw the flower" to "I saw the flour".
*   **Late Context:** A word at the start of a sentence might change based on a word at the end (e.g., "There" -> "Their").
*   **Probability Thresholds:** Models often output "unstable" partial results. If the UI updates on every unstable result, the text will appear to "vibrate" or "flicker" as the model toggles between two high-probability candidates.

### Visualization of Flicker
1.  T+0ms: "The..."
2.  T+100ms: "The cat..."
3.  T+200ms: "The car..." (Flicker: 'cat' becomes 'car')
4.  T+300ms: "The car is..."
5.  T+400ms: "The cart is..." (Flicker: 'car' becomes 'cart')

### Strategy to Reduce Flicker
*   **Stability Filtering:** Only update the keyboard buffer when the model's confidence for a word exceeds a threshold (e.g., 90%) or when the "unstable" suffix is separated from the "stable" prefix.
*   **Hysteresis:** Wait for a short "silence" or a specific number of tokens before committing a retype to the UI.
