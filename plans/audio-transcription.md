# Implementation Plan: Audio Transcription Feature

This plan outlines the steps to implement batch audio transcription for `harp` by integrating the OpenRouter API. This involves updating dependency management, configuration handling, API client implementation, and the daemon's recording flow.

## Phase 1: Dependency and Configuration
- [ ] **Dependency Update**:
    - [ ] Add `python-dotenv` to `pyproject.toml`.
    - [ ] Add `AsyncOpenAI` from `openai` if not already present.
- [ ] **Config Update (`src/harp/config.py`)**:
    - [ ] Import `load_dotenv` and call it at the module level.
    - [ ] Update `HarpConfig` to use the `HARP_` prefix:
        - `HARP_API_KEY`
        - `HARP_API_BASE_URL` (Default: `https://openrouter.ai/api/v1`)
        - `HARP_API_MODEL` (Default: `openai/gpt-audio-mini`)

## Phase 2: API Client Implementation (`src/harp/api.py`)
- [ ] **Implement `OpenRouterClient`**:
    - [ ] Initialize `AsyncOpenAI` in `__init__`.
    - [ ] Implement `async def transcribe(self, audio_data: np.ndarray, samplerate: int) -> str`:
        - Scale `float32` [-1.0, 1.0] to `int16`.
        - Write to an in-memory `io.BytesIO` buffer using the `wave` module.
        - Call `self.client.audio.transcriptions.create` with the buffer and the configured model.
        - Return the resulting text.

## Phase 3: Daemon Integration (`src/harp/daemon.py`)
- [ ] **Update `HarpDaemon`**:
    - [ ] Initialize `HarpConfig` and `OpenRouterClient` in `__init__`.
    - [ ] Refactor `_stop_recording(self)` to be **async**:
        - Transition state to `PROCESSING`.
        - Retrieve `audio_data` and call `await self.api_client.transcribe(...)`.
        - Print the transcribed text to the console.
        - Transition state back to `IDLE`.
    - [ ] Update `_toggle_state()` and `_handle_events()` to `await` the async `_stop_recording`.
    - [ ] **Cleanup**: Remove the temporary `_save_wav` method.

## Phase 4: Validation and Testing
- [ ] **Environment Setup**: Create a `.env` file with a valid `HARP_API_KEY`.
- [ ] **Manual Testing**:
    - [ ] Run `uv run harp`.
    - [ ] Record a short sentence and verify it is transcribed and printed to the console.
    - [ ] Verify the daemon transitions correctly between states (`RECORDING` -> `PROCESSING` -> `IDLE`).

## Technical Details
- **In-Memory Payloads**: Using `io.BytesIO` avoids unnecessary disk I/O and temporary file management.
- **Asynchronicity**: `AsyncOpenAI` and async daemon methods ensure the hotkey listener remains responsive during the API call.
- **Scaling**: Standard `int16` conversion is required for the `wave` module to produce a valid WAV buffer.
