import numpy as np
import traceback
from harp.whisper import LocalWhisperEngine


def reproduce():
    print("Testing LocalWhisperEngine with auto/default...")
    audio = np.zeros(16000, dtype=np.float32)

    # Mirroring default config
    engine = LocalWhisperEngine(
        model_size="tiny", device="auto", compute_type="default"
    )

    try:
        print("Calling transcribe (which calls load_model)...")
        result = engine.transcribe(audio)
        print(f"Success! Result: '{result}'")
    except Exception as e:
        print("\n--- CAUGHT ERROR ---")
        print(f"Error Type: {type(e)}")
        print(f"Error Message: {e}")
        traceback.print_exc()
        print("---------------------\n")


if __name__ == "__main__":
    reproduce()
