# Current Implementation Hurdles for Interactive Transcription in Harp

This report analyzes the core challenges and performance bottlenecks in the current implementation of interactive transcription within the `harp` project. The system utilizes a 'backspace-and-retype' strategy to simulate real-time text updates as audio is transcribed from a growing buffer.

## 1. Performance and Reliability of 'Backspace-and-Retype' (Wayland vs. X11)

The 'backspace-and-retype' strategy relies on the ability of the daemon to inject input into the system-wide event stream and have the target application process it quickly and accurately.

### Architectural Performance Differences
- **Wayland (uinput/evdev):** `harp` uses the kernel-level `uinput` subsystem to create a virtual keyboard. While `uinput` itself is extremely low-latency, the performance bottleneck on Wayland often arises from the compositor (e.g., GNOME's Mutter, KDE's KWin). Many modern compositors enforce a **single-frame synchronization (V-Sync)** for input events, adding roughly 8–16ms of latency per event. For a 50-character correction requiring 100 events (Press + Release), this can cause noticeable "sliding" of text.
- **X11 (XTest/xdotool):** X11's input injection via the XTEST extension is historically faster for raw bursts of input. However, X11 suffers from the **'MappingNotify' Thundering Herd** problem. When a daemon types characters not present in the current keyboard layout, X11 often triggers a desktop-wide keyboard mapping refresh, causing the entire UI to "freeze" for several milliseconds, leading to dropped backspace events.

### Reliability and the 'Shadow State' Problem
- **State Desynchronization:** The most significant reliability hurdle is the lack of feedback from the target application. Since `harp` cannot "read" the text box it is typing into, it must maintain an internal **"shadow state"** of what has been typed. If the user manually types a single character or moves the cursor while the daemon is performing a backspace sequence, the shadow state becomes desynchronized. This results in the daemon deleting the wrong text or corrupting the existing document.
- **Focus Shifts:** In Wayland, if a user switches windows during a long correction sequence (which can take several hundred milliseconds), the remaining backspaces and corrected text are sent to the newly focused window, potentially causing unintended data loss in other applications.
- **Input Method (IME) Conflicts:** On many Wayland setups, the interaction between `uinput` virtual events and the system's IME (like IBus or Fcitx) can lead to "sticky keys" or double-entry issues, where a backspace is interpreted as a text selection or a formatting command.

## 2. Increasing Overhead of Re-transcribing the Accumulated Buffer

The current loop in `harp` "peeks" at the audio buffer and re-transcribes the entire accumulated audio for each update. This approach faces several scaling hurdles:

### Computational Complexity (O(N²))
- As the user continues to speak, the audio buffer grows. If transcription is performed every 500ms, the total compute cost over time grows quadratically. For a 30-second sentence, the system might perform 60 full transcriptions, with each transcription being longer than the last.
- **Whisper Inference Latency:** Models like OpenAI's Whisper (even 'Tiny' or 'Small') have a 30-second context window. As the buffer approaches 30 seconds, the inference time increases significantly, leading to a "lag" where the typed text falls several seconds behind the speaker.

### Redundant Processing and Resource Exhaustion
- Re-transcribing the entire buffer for every peek is redundant because the beginning of the sentence rarely changes after the first few seconds.
- Continuous full-buffer transcription leads to high CPU/GPU utilization, which can interfere with the audio capture process or the performance of the application being typed into, causing "stuttering" in both audio and input.

## 3. Edge Cases for 'Peeking' and Transcription Flickering

The 'peeking' strategy (transcribing unfinished audio) introduces several visual and logical inconsistencies:

### Whisper's Non-Monotonicity (The "Look-back" Effect)
- **Contextual Correction:** Large language models like Whisper use future context to refine past results. For example:
  - **Peek 1 (at 2s):** "The cat sat"
  - **Peek 2 (at 3s):** "The cats are on"
  - **The Problem:** The addition of "are on" changed "cat sat" to "cats are". The daemon must now backspace " cat sat" and type " cats are on". This causes the text to "jump" or "flicker" in the target application.
- **Ending Hallucinations:** When audio is cut mid-word during a peek, the model often produces "hallucinations" (e.g., guessing the end of a word incorrectly). Once the word is completed in the next peek, the correction logic triggers a flickering update.

### Punctuation and Capitalization Shifts
- As the sentence develops, the model might decide to add a comma earlier in the sentence or change the capitalization of the first word based on the final sentence structure.
- These subtle shifts are mathematically "better" transcriptions but are "visually expensive" because they require deleting and retyping large chunks of text, increasing the risk of desynchronization and user distraction.

### The "End-of-Buffer" Noise
- Small noises or silence at the very end of the current peek can confuse the transcription engine, leading to junk output (e.g., "..." or repeated words) that is only corrected once the speaker continues or more silence is captured. This leads to rapid "type-and-delete" cycles that appear as high-frequency flickering.
