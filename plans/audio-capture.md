# Implementation Plan: Audio Capture Feature

This plan outlines the steps to implement non-blocking audio capture in the `harp` daemon during the `RECORDING` state and save the result to a timestamped WAV file in the user's home directory.

## Phase 1: Core Audio Implementation (`src/harp/audio.py`)
- [ ] **Update `AudioStreamer`**:
    - [ ] Initialize `self._stream: sd.InputStream | None = None` and `self.audio_buffer: list[np.ndarray] = []`.
    - [ ] Implement `_callback(self, indata, frames, time, status)` to append copies of `indata` to `self.audio_buffer`.
    - [ ] Implement `start_recording()`:
        - Clear `self.audio_buffer`.
        - Create and start a new `sd.InputStream` (16kHz, Mono, float32) with the callback.
    - [ ] Implement `stop_recording()`:
        - Stop and close `self._stream`.
        - Concatenate `self.audio_buffer` using `np.concatenate` and return the resulting `numpy` array.

## Phase 2: Daemon Integration (`src/harp/daemon.py`)
- [ ] **State Transition Refactoring**:
    - [ ] Add `self.audio_streamer = AudioStreamer()` to `HarpDaemon.__init__`.
    - [ ] Implement `_start_recording(self)` helper:
        - Transition to `RECORDING`.
        - Call `self.audio_streamer.start_recording()`.
        - Print "capturing" and send a notification.
    - [ ] Implement `_stop_recording(self)` helper:
        - Transition to `IDLE`.
        - Call `self.audio_streamer.stop_recording()`.
        - Trigger the `_save_wav` process.
    - [ ] Implement `_save_wav(self, audio_data)`:
        - Scale `float32` [-1.0, 1.0] to `int16`.
        - Use the `wave` module to write to `~/harp_test_TIMESTAMP.wav`.
- [ ] **Hook Integration**: Update `_toggle_state()` and `_handle_events()` to use the new `_start_recording` and `_stop_recording` helpers.

## Phase 3: Validation and Testing
- [ ] **Dependency Check**: Ensure `libportaudio2` is installed on the system (`sudo apt install libportaudio2`).
- [ ] **Manual Testing**:
    - [ ] Run `uv run harp`.
    - [ ] Toggle or hold `Ctrl + Space` to record.
    - [ ] Verify the "idle" notification and the presence of the `.wav` file in `~/`.
    - [ ] Play back the recorded file to confirm audio quality.

## Technical Details
- **Non-blocking I/O**: `sounddevice.InputStream` with a callback ensures the `asyncio` loop is not blocked during audio capture.
- **Conversion**: Audio data is captured as `float32` and converted to `int16` for standard WAV compatibility.
- **Sample Rate**: Defaulting to 16,000Hz as requested, optimal for Whisper/OpenRouter STT.
