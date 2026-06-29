"""harp — Linux-native dictation library."""

from harp.audio import AudioSource, FileSource, MicrophoneSource
from harp.events import TranscriptEvent
from harp.session import HarpSession

__version__ = "0.8.1"

__all__ = [
    "AudioSource",
    "FileSource",
    "HarpSession",
    "MicrophoneSource",
    "TranscriptEvent",
    "__version__",
]
