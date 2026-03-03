#!/usr/bin/env python3
"""
Utility to record the ground truth audio for integration testing.
"""

import os
import sys
import time
import wave

import numpy as np

# Add src to path to import harp
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from harp.audio import AudioStreamer

TEXT_FILE = "tests/assets/ground_truth.txt"
OUTPUT_FILE = "tests/assets/ground_truth.wav"


def record():
    if not os.path.exists(TEXT_FILE):
        print(f"Error: {TEXT_FILE} not found. Please ensure the assets exist.")
        return

    with open(TEXT_FILE, "r") as f:
        text = f.read().strip()

    print("\n" + "=" * 60)
    print("GROUND TRUTH RECORDING")
    print("=" * 60)
    print("\nYou will read the following text:\n")
    print(f'"{text}"')
    print("\n" + "=" * 60)

    input("\nPress Enter to start the 3-second countdown...")

    for i in range(3, 0, -1):
        print(f"Starting in {i}...")
        time.sleep(1)

    print("\n>>> RECORDING... (Press Enter to stop) <<<\n")

    streamer = AudioStreamer(samplerate=16000)
    streamer.start_recording()

    try:
        input()
    except KeyboardInterrupt:
        pass

    audio_data = streamer.stop_recording()
    print(f"\nRecording stopped. Captured {len(audio_data) / 16000:.2f} seconds.")

    # Convert float32 to int16 for WAV
    audio_int16 = (np.clip(audio_data, -1.0, 1.0) * 32767).astype(np.int16)

    # Ensure directory exists
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    with wave.open(OUTPUT_FILE, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 2 bytes for int16
        wf.setframerate(16000)
        wf.writeframes(audio_int16.tobytes())

    print(f"\nSaved to: {OUTPUT_FILE}")
    print("Recording utility ready for use.")


if __name__ == "__main__":
    record()
