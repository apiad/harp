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
        compute_type: str = "int8",
        download_root: Optional[str] = None,
    ) -> None:
        """
        Initializes the Whisper model and keeps it in memory.

        Args:
            model_size: Size of the model (e.g., 'tiny', 'base', 'small').
            device: Device to use ('cpu', 'cuda', 'auto').
            compute_type: Quantization type ('int8', 'float16', 'int8_float16').
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
            self.model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
                download_root=self.download_root,
            )

    def transcribe(self, audio_data: np.ndarray) -> str:
        """
        Transcribes the given audio data.

        Args:
            audio_data: Float32 numpy array of audio samples (16kHz mono).

        Returns:
            The transcribed text.
        """
        if self.model is None:
            self.load_model()

        segments, _ = self.model.transcribe(
            audio_data,
            beam_size=5,
            vad_filter=False,  # VAD is handled by the user manually or not at all as requested
        )

        text_segments = [segment.text for segment in segments]
        return "".join(text_segments).strip()

    @staticmethod
    def list_local_models(download_root: Optional[str] = None) -> List[str]:
        """
        Lists models available in the local cache.
        """
        root = Path(download_root or (Path.home() / ".cache" / "harp" / "models"))
        if not root.exists():
            return []

        # faster-whisper stores models in subdirectories
        return [d.name for d in root.iterdir() if d.is_dir()]

    @staticmethod
    def download(model_size: str, download_root: Optional[str] = None) -> str:
        """
        Downloads a specific model size.
        """
        root = download_root or str(Path.home() / ".cache" / "harp" / "models")
        return download_model(model_size, output_dir=root)
