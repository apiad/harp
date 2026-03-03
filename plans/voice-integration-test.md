# Plan: Voice-Based Integration Test

## Objective
Implement an end-to-end integration test that uses a live recording of the user's voice to verify transcription accuracy against a challenging "ground truth" text.

## Assets & Files
1.  **`tests/assets/ground_truth.txt`**: Contains the philosophical text to be read.
2.  **`tests/assets/ground_truth.wav`**: (Generated once) Reference audio recording.
3.  **`scripts/record_ground_truth.py`**: Utility to record the WAV file.
4.  **`tests/test_integration_end_to_end.py`**: Pytest file for the integration check.

## Text to Record
> "Existence is not a static monolith, but a shimmering, flickering resonance of choices made in the silence between heartbeats. We often ask: 'Why are we here?' as if the universe were a ledger waiting to be balanced. But perhaps the meaning isn't found in the grand orchestration of the cosmos, but in the jagged, syncopated rhythms of our individual struggles. Consider the word 'ephemeral'—it tastes like autumn leaves on the tongue, yet it carries the weight of every lost sunset. In the cacophony of modern life, where data flows like a torrential downpour, do we still hear the quiet hum of our own curiosity? To seek, to err, to persevere—these are the quintessences of the human condition. Whether we are chasing shadows in a digital labyrinth or simply breathing in the scent of rain on dry earth, the significance is not in the destination, but in the deliberate act of being present. Life is an improvisation, a jazz solo played on the strings of entropy, where every pause is a question and every breath is a defiant answer. So, we continue to dance, oblivious to the void, finding solace in the beautiful, chaotic absurdity of it all."

## Step-by-Step Execution

### Step 1: Initialize Assets
- Create `tests/assets/` directory.
- Write the text above to `tests/assets/ground_truth.txt`.

### Step 2: Create Recording Script
- Implement `scripts/record_ground_truth.py`.
- Features: 
    - Display text.
    - 3-second countdown.
    - Record until user hits 'Enter' or for a fixed duration (~60s).
    - Save to `tests/assets/ground_truth.wav` using `sounddevice` and `wave`.

### Step 3: Add Comparison Dependencies
- Add `fuzzywuzzy` and `python-Levenshtein` to `pyproject.toml` (dev dependencies).

### Step 4: Implement Integration Test
- Create `tests/test_integration_end_to_end.py`.
- Logic:
    - Load `ground_truth.wav`.
    - Use `OpenRouterClient` to transcribe (Live API).
    - Load `ground_truth.txt`.
    - Normalize both (lowercase, remove punctuation).
    - Assert `fuzz.ratio` > 90%.

### Step 5: Manual Action
- User runs `uv run scripts/record_ground_truth.py`.
- User reads the text.
- Recording is saved.

### Step 6: Validation
- Run `uv run pytest tests/test_integration_end_to_end.py`.
