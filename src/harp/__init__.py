"""harp — Linux-native dictation library."""

from harp.audio import AudioSource, FileSource, MicrophoneSource
from harp.dictation import DictationSession
from harp.events import TranscriptEvent
from harp.session import HarpSession

__version__ = "0.10.1"

__all__ = [
    "AudioSource",
    "DictationSession",
    "FileSource",
    "HarpSession",
    "MicrophoneSource",
    "TranscriptEvent",
    "__version__",
]
