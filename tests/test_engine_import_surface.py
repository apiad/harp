"""The streaming engine must import without desktop/daemon deps.

warden installs harp engine-only (faster-whisper + numpy). ``import harp``
must not pull ``sounddevice`` (PortAudio) at module load — only
``MicrophoneSource`` needs it, lazily.

The import check runs in a subprocess so it observes a genuinely fresh
interpreter and never mutates this process's ``sys.modules``.
"""
import subprocess
import sys


def test_import_harp_does_not_load_sounddevice():
    code = (
        "import sys; import harp, harp.session, harp.streaming, harp.vad; "
        "assert 'sounddevice' not in sys.modules, "
        "'importing harp pulled sounddevice; make it lazy in audio.py'"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_engine_public_surface_importable():
    from harp import AudioSource, FileSource, HarpSession, TranscriptEvent  # noqa: F401
    from harp.vad import NullDetector, SileroDetector  # noqa: F401
