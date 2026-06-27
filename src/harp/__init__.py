"""harp — Linux-native dictation library."""

from harp.audio import AudioSource, MicrophoneSource
from harp.events import TranscriptEvent
from harp.session import HarpSession

__version__ = "0.7.0"

__all__ = [
    "AudioSource",
    "HarpSession",
    "MicrophoneSource",
    "TranscriptEvent",
    "__version__",
]
