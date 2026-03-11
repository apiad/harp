import numpy as np
from harp.whisper import LocalWhisperEngine


def reproduce():
    print("Testing LocalWhisperEngine with int8 on CPU...")
    # Mock some audio (1 second of silence)
    audio = np.zeros(16000, dtype=np.float32)

    try:
        # Use the current default settings
        engine = LocalWhisperEngine(
            model_size="tiny", device="cpu", compute_type="int8"
        )
        print("Engine initialized. Attempting transcription...")
        result = engine.transcribe(audio)
        print(f"Success! Result: '{result}'")
    except Exception as e:
        print(f"Caught expected error: {e}")


if __name__ == "__main__":
    reproduce()
