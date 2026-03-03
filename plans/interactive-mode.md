# Implementation Plan: Interactive Mode

This plan outlines the implementation of "Interactive Mode" for `harp`, enabling real-time transcription feedback by periodically sampling audio and updating the typed text using backspaces for refinements.

## Phase 1: Core Component Extensions

### 1. Audio Streamer (`src/harp/audio.py`)
- [ ] Implement `get_current_buffer() -> np.ndarray`:
    - Returns a concatenation of the current `audio_buffer` without stopping or closing the `sd.InputStream`.
    - This allows the daemon to "peek" at the audio accumulated so far.

### 2. Wayland Typer (`src/harp/input.py`)
- [ ] **Backspace Support**: Add `backspace(count: int)` method to emit `KEY_BACKSPACE` events.
- [ ] **Text Filtering Helper**: Move character filtering logic (safe vs full) into a reusable method `filter_text(text: str) -> str` so it can be used consistently during interactive updates.
- [ ] **Async Support**: Transition `type_text` and `backspace` to be `async` if necessary to ensure they don't block the `asyncio` loop for long strings.

## Phase 2: CLI and Configuration

### 1. CLI Updates (`src/harp/__main__.py`)
- [ ] Add `--interactive` / `-i` boolean flag.
- [ ] Add `--interval` float option (default `2.0`).
- [ ] Pass these values to the `HarpoDaemon` constructor.

### 2. Config Updates (`src/harp/config.py`)
- [ ] Add `interactive` and `sampling_interval` to `HarpoConfig` (optional, for persistent defaults).

## Phase 3: Daemon Logic (`src/harp/daemon.py`)

### 1. State Management
- [ ] Add `self.current_session_text: str = ""` to track what has been typed in the current recording session.
- [ ] Add `self._interactive_task: asyncio.Task | None = None` to manage the background loop.

### 2. Interactive Loop
- [ ] Implement `_interactive_loop()`:
    - While in `RECORDING` state:
        - Wait for `sampling_interval` seconds.
        - Peek at the current audio buffer using `audio_streamer.get_current_buffer()`.
        - Request transcription from `api_client`.
        - **Update Logic**:
            - Let `new_text` be the filtered transcription.
            - If `new_text` starts with `self.current_session_text`:
                - Type only the suffix: `new_text[len(self.current_session_text):]`.
            - Else:
                - Backspace everything: `backspace(len(self.current_session_text))`.
                - Type `new_text` from the beginning.
            - Update `self.current_session_text = new_text`.

### 3. Integration
- [ ] Start `_interactive_loop` in `_start_recording`.
- [ ] Cancel `_interactive_task` and clear `current_session_text` in `_stop_recording`.
- [ ] Ensure the final transcription at the end of recording correctly reconciles with the last interactive update.

## Phase 4: Validation and Testing
- [ ] **Responsiveness**: Verify that the daemon remains responsive to the "release" event while a transcription is in flight.
- [ ] **Accuracy**: Test with sentences that refine over time (e.g., Whisper changing "He" to "Hello" as more context arrives) to verify backspacing works.
- [ ] **Recursive Prevention**: Ensure the virtual keyboard remains excluded from discovery.

## Technical Details
- **Concurrency**: Use `asyncio.create_task` for the loop to allow the main `evdev` handler to continue listening for the key-up event.
- **Race Conditions**: Use a lock or check state before applying interactive updates to avoid typing after the user has already released the hotkey.
