# Full (dictation) mode — record-then-transcribe

**Date:** 2026-07-02
**Status:** design — approved for planning
**Repos:** harp (new `DictationSession` primitive) + aegis (consumer rewrite)

## Motivation

harp today has exactly one transcription orchestration: the VAD-segmented
**incremental** streaming engine (`HarpSession`), built for *unbounded*
long-form audio (meetings, lectures, file transcription). It finalizes chunks
at silence boundaries and drops finalized audio so a long recording streams out
as you go.

Push-to-talk **dictation** is a different problem: a *bounded* utterance that
ends when the user releases the key. Driving it through the incremental engine
produced a cascade of defects — 10s warm-up before any text, a dropped last
sentence on stop, degraded decoding without `transcribe_segments`, chunk seams.
Every one of these is a symptom of using a long-form engine for short-form work.

The local dictation apps (Superwhisper, AudioPen offline, Wispr) do **not**
stream for dictation. They **record while the key is held, then transcribe the
whole clip once on release** against a warm model. It is simpler, higher
quality (full context, no seams), and structurally free of the bugs above.

## The dividing line: bounded vs unbounded

- **Unbounded** audio (could run for an hour) → you *cannot* wait for the end,
  so you must segment and finalize incrementally. This is `HarpSession`.
- **Bounded** audio (ends on key release) → you *can* wait, so you buffer and
  do one clean decode. This is the new `DictationSession`.

If you know when the utterance ends, incremental complexity buys nothing.

## Architecture

Two explicit, single-purpose session classes sharing the same primitives
(`AudioSource`, `LocalWhisperEngine`, `_bytes_to_float32`, the model cache) but
**not** their orchestration.

### harp: `src/harp/dictation.py` — `DictationSession`

```python
class DictationSession:
    def __init__(
        self,
        audio: AudioSource,
        transcribe: TranscribeFn,            # a WARM engine's transcribe
        language: str | None = None,
        on_partial: Callable[[str], None] | None = None,  # reserved, inert in v1
        max_seconds: float = 120.0,          # safety cap
    ) -> None: ...

    def start(self) -> None:      # spawn a thread that buffers mic frames
    def stop(self) -> str:        # stop, drain buffer, decode once, return text
    @property
    def final_text(self) -> str: ...
```

Behavior:

- `start()` spawns a worker thread that pulls frames from `audio.frames()` and
  appends them to an in-memory list of PCM bytes. **No decoding while
  recording** — the worker only accumulates. It stops when the source ends,
  `stop()` is called, or `max_seconds` of audio has been buffered.
- `stop()` is thread-safe and idempotent. It signals the worker, closes the
  audio source, joins, then concatenates the buffered frames into one float32
  array and calls `transcribe(audio, None, language)` **exactly once**, storing
  and returning the result. The `MicrophoneSource` drain-on-close fix already
  landed guarantees no captured frame is lost, so the tail is always complete.
- `transcribe` is injected — the consumer holds a long-lived, pre-loaded
  `LocalWhisperEngine`, so harp needs **no** warmth machinery. The model-warmth
  problem is solved by the consumer keeping the engine alive (daemon pattern).
- `on_partial` is in the signature but **not wired** in v1. Partials become a
  purely additive change later (a periodic re-decode thread calling it) with no
  API churn.
- `max_seconds` caps the buffer so a stuck session can't grow without bound;
  reaching it ends recording as if `stop()` were called.

No VAD, no warm-up, no chunk/step cadence, no overlap/seam logic. By
construction none of the incremental-mode defects can occur here.

### aegis: rewrite the voice path to consume `DictationSession`

- `aegis.voice.session.VoiceSession` wraps `DictationSession` instead of
  `HarpSession`. The streaming machinery — `call_soon_threadsafe` marshalling,
  committed/transient delta bookkeeping, `_apply_voice_text` incremental append
  — is **removed**. There are no incremental updates.
- `ctrl+g` start → `VoiceSession.start()` → `DictationSession.start()`. The
  origin pane's `GrowingInput` is captured and the recording indicator shown.
- `ctrl+g` stop → `VoiceSession.stop()`. The decode (~0.3–1s for a short clip)
  runs **off the UI thread** (in a worker/executor); the final text is then
  marshalled back onto the UI loop and inserted at the origin input in **one**
  shot (appended to any pre-existing content, per the anchoring rule). Indicator
  cleared. Never auto-submitted.
- **Kept from current work:** startup **prewarm** (still need a warm engine),
  `device="cpu"` + `compute_type="default"` + ctranslate2 log-silencing (still
  prevents TUI corruption regardless of mode), the `voice:` config block,
  packaging (`aegis[voice]`), feature detection.
- **Dropped as obsolete:** `warmup=0`, `transcribe_segments`, and
  transient-preview plumbing in `_default_factory` — meaningless in full mode.
  The factory now builds a `DictationSession`.

## Data flow

```
ctrl+g ─► VoiceSession.start ─► DictationSession.start
              worker thread: for frame in mic.frames(): buffer.append(frame)   (no decode)
ctrl+g ─► VoiceSession.stop ─► DictationSession.stop
              close mic ─► drain buffer ─► concat ─► transcribe(whole clip) ONCE ─► text
          text ──(marshal to UI loop)──► insert at origin GrowingInput (one shot)
```

## Error handling

- **Empty/no speech:** `stop()` on an empty buffer returns `""`; aegis inserts
  nothing and clears the indicator.
- **Decode failure:** `DictationSession.stop()` lets the transcribe exception
  surface; aegis catches it, shows a one-line status, leaves the input
  untouched, clears the indicator.
- **Mic open failure / deps missing:** unchanged from current aegis handling
  (feature-detect + status hint).
- **`max_seconds` reached:** recording ends and decodes what was captured — no
  error, just a bounded result.
- **App teardown mid-recording:** aegis stops the session on unmount.

## Testing

harp (`tests/test_dictation.py`):
- Fake `AudioSource` (scripted frames) + fake `transcribe` → assert the buffer
  is decoded **once** and only on `stop()` (transcribe call count == 1, zero
  calls during recording).
- Stop drains the full buffer: source with N queued frames → decoded audio
  length == N·framesize (tail complete).
- `stop()` idempotent; second call returns the same text, no re-decode.
- `max_seconds` cap ends recording and still returns a decode.
- Real-model integration test decoding `tests/assets/ground_truth.wav` through
  `DictationSession` (marked slow).

aegis (`tests/test_voice_action.py`, `tests/test_voice_factory.py`):
- `VoiceSession` over a stub `DictationSession` → `ctrl+g` start sets recording;
  `ctrl+g` stop inserts the final text once at the origin input (appended to
  existing content), clears the indicator; decode runs off the UI thread and the
  result is marshalled back.
- Factory builds a `DictationSession` (not `HarpSession`) with the warm engine
  and `cpu`/`default` pins.
- Unavailable-deps path unchanged.

## Rollout

1. **harp:** implement `DictationSession` (TDD), full suite green, release a new
   `harpio` version.
2. **aegis:** bump the `harpio` pin, rewrite `VoiceSession`/`_default_factory`
   to full mode, delete the obsolete streaming plumbing, keep prewarm + output
   silencing.

## Non-goals (v1)

- Live partials (hook reserved, inert).
- Auto-stop on silence (Claude Code's 15s idle) — the user controls start/stop;
  only `max_seconds` bounds it.
- Removing or changing incremental mode (`HarpSession`) — it stays for
  long-form/file transcription.
- LLM cleanup/rewrite of the transcript (AudioPen-style) — out of scope.
