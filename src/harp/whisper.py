"""
Local transcription engine using faster-whisper.
"""

import os
from pathlib import Path
from typing import List, Optional

import numpy as np
from faster_whisper import WhisperModel, download_model


class LocalWhisperEngine:
    """
    Manages local Whisper inference for high-performance transcription.
    """

    def __init__(
        self,
        model_size: str = "base",
        device: str = "auto",
        compute_type: str = "default",
        download_root: Optional[str] = None,
    ) -> None:
        """
        Initializes the Whisper model and keeps it in memory.

        Args:
            model_size: Size of the model (e.g., 'tiny', 'base', 'small').
            device: Device to use ('cpu', 'cuda', 'auto').
            compute_type: Quantization type ('int8', 'float16', 'int8_float16', 'default').
            download_root: Directory to store downloaded models.
        """
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type

        if download_root is None:
            self.download_root = str(Path.home() / ".cache" / "harp" / "models")
        else:
            self.download_root = download_root

        # Ensure the download directory exists
        os.makedirs(self.download_root, exist_ok=True)

        self.model: Optional[WhisperModel] = None

    def load_model(self) -> None:
        """
        Loads the model into memory.
        """
        if self.model is None:
            # Check if model exists in subdirectory first
            model_path = Path(self.download_root) / self.model_size
            if (model_path / "model.bin").exists():
                load_path = str(model_path)
            else:
                load_path = self.model_size

            self.model = WhisperModel(
                load_path,
                device=self.device,
                compute_type=self.compute_type,
                download_root=self.download_root,
            )

    def transcribe(
        self,
        audio_data: np.ndarray,
        initial_prompt: Optional[str] = None,
        language: Optional[str] = None,
    ) -> str:
        """
        Transcribes the given audio data.

        Args:
            audio_data: Float32 numpy array of audio samples (16kHz mono).
            initial_prompt: Optional text to bias the transcription context.
            language: Optional language code (e.g., 'en', 'es').

        Returns:
            The transcribed text.
        """
        try:
            if self.model is None:
                self.load_model()

            segments, _ = self.model.transcribe(
                audio_data,
                beam_size=5,
                initial_prompt=initial_prompt,
                language=language,
                vad_filter=False,  # VAD is handled by the user manually or not at all as requested
            )

            text_segments = [segment.text for segment in segments]
            return "".join(text_segments).strip()

        except Exception as e:
            # Catch specific hardware/library errors (CUDA, int8, float16)
            err_msg = str(e).lower()
            is_compute_error = any(
                x in err_msg for x in ["compute type", "int8", "float16"]
            )
            is_cuda_error = any(x in err_msg for x in ["cuda", "cublas", "cudnn"])

            # If we are not already on CPU/default, try falling back
            if (is_compute_error or is_cuda_error) and (
                self.device != "cpu" or self.compute_type != "default"
            ):
                print(
                    f"Warning: {e}. Falling back to device='cpu' and compute_type='default'."
                )
                self.device = "cpu"
                self.compute_type = "default"
                self.model = None  # Force reload
                return self.transcribe(audio_data, initial_prompt, language)
            else:
                raise e

    @staticmethod
    def list_local_models(download_root: Optional[str] = None) -> List[str]:
        """
        Lists models available in the local cache.
        """
        root = Path(download_root or (Path.home() / ".cache" / "harp" / "models"))
        if not root.exists():
            return []

        models = []
        for d in root.iterdir():
            if d.is_dir() and not d.name.startswith("."):
                # A valid model directory should have model.bin
                # (either directly or in a snapshot subfolder for HF layout)
                if (d / "model.bin").exists() or any(d.glob("snapshots/*/model.bin")):
                    models.append(d.name)
        return models

    @staticmethod
    def download(model_size: str, download_root: Optional[str] = None) -> str:
        """
        Downloads a specific model size.
        """
        root = Path(download_root or (Path.home() / ".cache" / "harp" / "models"))
        model_dir = root / model_size
        return download_model(model_size, output_dir=str(model_dir))
