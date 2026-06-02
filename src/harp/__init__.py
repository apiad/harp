"""harp — Linux-native dictation library."""

from harp.audio import AudioSource, MicrophoneSource
from harp.events import CommitEvent
from harp.session import HarpSession

__version__ = "0.7.0"

__all__ = [
    "AudioSource",
    "CommitEvent",
    "HarpSession",
    "MicrophoneSource",
    "__version__",
]
