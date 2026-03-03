# Plan: Overhaul Interactive Mode

## Objective
Implement a robust, near-real-time transcription system using Gemini 1.5 Flash via OpenRouter. The system will use a rolling window of audio, a dual-buffer UX (HUD for unstable text, direct typing for committed text), and prevent "input fighting" via physical keypress detection.

## Architectural Impact
- **State & Audio Management**: Transition to a rolling 5-second audio window with 1-second overlaps, sent every 1-2 seconds.
- **UI & Feedback**: Introduction of a floating HUD (e.g., using `tkinter` or `PyGObject`) to display "Interim Text" without typing it into the active window.
- **Input Strategy**: Use a "minimal-diff" (Longest Common Prefix) algorithm for "Committed Text" to minimize backspacing.
- **Safety Mechanism**: Use `pynput` to detect user typing and pause the daemon's automated typing.
- **Backend**: Gemini 1.5 Flash via OpenRouter with "delta prompting".

## File Operations

### Files to Modify
1.  **`src/harp/api.py`**: Update `OpenRouterClient` to support "delta" transcription with context.
2.  **`src/harp/audio.py`**: Add `get_rolling_window(seconds)` to `AudioStreamer`.
3.  **`src/harp/input.py`**: Add `type_diff(old_text, new_text)` to `WaylandTyper`.
4.  **`src/harp/daemon.py`**: 
    - Overhaul `_interactive_loop` with "Local Agreement" logic.
    - Integrate `pynput` listener for typing safety.
5.  **`pyproject.toml`**: Add `pynput` and `tkinter` (if needed) dependencies.

### Files to Create
1.  **`src/harp/hud.py`**: A lightweight, non-focusing overlay window for interim text.

## Step-by-Step Execution

### Step 1: Update API and Audio Chunking
- **Audio Windowing**: Implement `get_rolling_window` in `audio.py`.
- **Delta Prompting**: Update `api.py` with instructions for Gemini 1.5 Flash to output ONLY new words.

### Step 2: Input Safety and Minimal-Diff Typing
- **Safety Listener**: Use `pynput.keyboard.Listener` in `daemon.py` to manage a `pause_typing` flag.
- **Minimal-Diff**: Implement `type_diff` using LCP calculation in `input.py`.

### Step 3: Create the Floating HUD
- **HUD Component**: Create `src/harp/hud.py`. Ensure it is non-blocking and runs on a separate thread if necessary.

### Step 4: Overhaul the Daemon Loop
- **Dual-Buffer Logic**:
    - Update HUD with full `interim_text`.
    - Apply "Local Agreement" (2-pass match) before moving text to the `committed_text` buffer.
    - Call `type_diff` only when `pause_typing` is False.

### Step 5: Validation
- Unit tests for `type_diff` and Local Agreement logic.
- Manual verification of typing safety and HUD responsiveness.
