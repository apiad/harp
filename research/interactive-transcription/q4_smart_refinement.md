# Smart Text Refinement and User Feedback Strategies

This document explores strategies for "smart" text refinement and managing user feedback in an interactive transcription daemon, specifically focusing on low-latency LLM stabilization, "ghost text" implementation, retroactive corrections, confidence heuristics, and input fighting prevention.

---

## 1. Low-Latency LLM as a 'Stabilizer'

Using a low-latency LLM (e.g., **Llama 3 on Groq** or **Gemini 1.5 Flash**) as a stabilizer helps decide when a transcription segment is "final" (ready to be committed) or "provisional" (still subject to change).

### Mechanisms for Stabilization
- **Semantic Endpointing**: Traditional Voice Activity Detection (VAD) relies on silence. An LLM can perform "semantic endpointing" by reading the current provisional buffer and determining if it constitutes a complete grammatical thought. If the LLM detects a natural sentence break, it signals the daemon to "Commit."
- **Grammatical Filtering**: ASR models often produce "word salad" in noisy environments. The LLM acts as a filter; if it can't find a plausible grammatical structure for a segment, that segment is held as "provisional" until more context arrives.
- **Predictive Stability**: If an LLM can predict the next likely word with high confidence (matching the ASR's next predicted token), the previous tokens are highly likely to be stable and can be finalized earlier.

### Implementation Strategy
1.  **Sliding Window**: Send the last 5-10 words of the "Interim" buffer to the LLM.
2.  **Prompt**: "Does the following text fragment look like a complete sentence? Respond with YES or NO. [Fragment]"
3.  **Thresholding**: If the LLM returns YES, or if the buffer length exceeds a certain token limit (e.g., 20 tokens), the segment is finalized.

---

## 2. Implementation of 'Ghost Text' (Unstable Text)

"Ghost Text" represents the daemon's current best guess for what the user is saying.

### The Two-Buffer Pattern
- **Committed Buffer (Immutable)**: Text that has passed stability thresholds. Once written to the target application, it is never changed (or only changed via explicit user action).
- **Interim Buffer (Volatile)**: The "Ghost Text." This is updated every ~100ms as the ASR emits partial results.

### UX implementation in a Background Daemon
Since a background daemon types into *other* applications (e.g., a text editor), standard CSS "opacity" for ghost text isn't possible.

- **The Floating HUD (Recommended)**: A small, semi-transparent overlay window (using `tkinter`, `PyQt`, or `electron`) follows the cursor or stays at the bottom of the screen. Ghost text is displayed here. Only when text is "committed" is it typed into the target application.
- **The "Backspace-and-Rewrite" (Dangerous)**: The daemon types the ghost text directly into the application. When the ASR updates its guess, the daemon sends `Backspace * N` and types the new guess.
    - *Risk*: High flicker and potential for data loss if the user clicks elsewhere or starts typing.
    - *Best for*: Dedicated terminal-based environments where `` (carriage return) can be used.

---

## 3. Dealing with Retroactive Corrections

When a model corrects a word from 5-10 seconds ago (a "deep correction"), the daemon must decide whether to go back and fix it.

### Best UX Practices
- **The "Depth" Threshold**:
    - **Shallow Corrections** (last 1-3 words): If the correction is within the last 3 words, the daemon should perform a silent correction (Backspace + Correct).
    - **Deep Corrections** (4+ words ago): **Do NOT perform silent corrections.** It is extremely jarring for a user to see text disappearing and changing far behind their current focus.
- **The "Mark-for-Review" Pattern**: Instead of fixing deep errors, the daemon can log them or (if using a HUD) highlight them in red for the user to fix manually later.
- **Contextual Delay**: Introduce a 1-2 second "commitment delay." Don't type anything until it is "stable" enough that the likelihood of a deep correction is <5%.

---

## 4. Heuristics for Confidence Scores

ASR models like Whisper and Gemini provide metadata that can trigger automatic backspacing.

### Key Metrics
- **Whisper `logprobs`**: Token-level log-probabilities.
    - *Heuristic*: If the average logprob of the last 3 tokens drops below `-1.0`, stop typing and wait for the "Common Prefix" to stabilize.
- **`no_speech_prob`**:
    - *Heuristic*: If `no_speech_prob > 0.6`, ignore the current segment (it's likely background noise/hallucination).
- **Local Agreement (UFAL-Whisper)**:
    - *Heuristic*: Maintain a buffer of the last 3 ASR passes. Only "Commit" a word if it is identical in all 3 passes. If the word changes in the 4th pass, trigger a backspace correction for that specific word.
- **Common Prefix**: In beam search, only tokens shared by all active beams are "safe." All others are "volatile."

---

## 5. Minimizing 'Input Fighting' (User Presence Detection)

"Input fighting" occurs when the daemon and the user try to type in the same field simultaneously.

### Detection & Mitigation
- **Global Keyboard Hook (`pynput`)**:
    - Use a global listener to detect any physical keypress from the user.
    - **Pause Protocol**: On any keypress, the daemon immediately stops its "Typing Thread" and sets a `pause_event`.
    - **Resume Protocol**: Use an "Idle Timer" (e.g., 2.0 - 5.0 seconds). Only resume automated typing when no physical keyboard activity has been detected for the duration of the timer.
- **Buffer Flushing**: When a user starts typing, the daemon should **clear its Interim Buffer**. This prevents the daemon from "finishing" a sentence that the user has already manually corrected or moved on from.
- **Focus Tracking**: (OS-specific) Check if the "Active Window" has changed. If the user clicks away to a different app, the daemon should pause typing to avoid leaking transcribed text into the wrong window.

### Example Implementation Snippet (Python)
```python
import threading
import time
from pynput import keyboard

class TypingDaemon:
    def __init__(self):
        self.paused = False
        self.last_user_activity = 0
        self.idle_threshold = 2.0 # seconds
        self.pause_event = threading.Event()
        self.pause_event.set()

    def on_press(self, key):
        self.last_user_activity = time.time()
        if not self.paused:
            print("User typing detected! Pausing...")
            self.paused = True
            self.pause_event.clear()

    def monitor_idle(self):
        while True:
            if self.paused and (time.time() - self.last_user_activity > self.idle_threshold):
                print("User idle. Resuming...")
                self.paused = False
                self.pause_event.set()
            time.sleep(0.5)

    def typing_loop(self):
        while True:
            self.pause_event.wait()
            # ... Logic to type committed text ...
            time.sleep(0.1)
```

---

## Summary of Recommendations

| Feature | Best Practice |
| :--- | :--- |
| **Stabilizer** | Use Llama 3 (Groq) for semantic endpointing (detecting end of thoughts). |
| **Ghost Text** | Use a **Floating HUD Overlay** rather than direct typing into apps. |
| **Retroactive Fixes** | Only backspace for the last ~3 words; flag deeper errors for manual review. |
| **Confidence** | Use **Local Agreement** (3-pass match) before committing text. |
| **Input Fighting** | Use `pynput` with a 2-second idle resume timer. |
