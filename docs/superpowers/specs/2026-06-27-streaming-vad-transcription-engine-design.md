# Streaming VAD-Segmented Transcription Engine

**Date:** 2026-06-27
**Status:** Approved design — ready for implementation planning
**Repo:** `repos/harp`

## Problem

Harp today is mic-only and its streaming core (`StreamingTranscriber` in
`src/harp/streaming.py`) re-decodes a rolling window (default 30s) with
`beam_size=5` every `slide_interval` (1s), committing via LocalAgreement-2.
Two consequences make it unfit for **long-running audio**:

1. **Unbounded / growing re-decode cost.** Each step re-decodes the whole
   buffer up to `window` seconds. On CPU a 30s beam-5 decode can exceed the
   slide interval, so the engine falls behind real time. Already-finalized
   speech keeps getting re-decoded.
2. **No permanent finalization.** `_maybe_trim` only keeps a fixed `overlap`
   and resets agreement state; there is no notion of "this chunk is done,
   drop its audio and never touch it again."

There is also no way to transcribe a **pre-recorded file** incrementally —
`AudioSource` is a `Protocol` but `MicrophoneSource` is the only
implementation.

## Goal

Move harp to a **default streaming mode** built around a library-first engine
that:

- Buffers a short **warm-up** (short utterances stay a single clean decode,
  exactly like today's dictation).
- Past warm-up, enters **chunked streaming**: finds safe cut points, decodes
  each completed chunk **exactly once** (with prior text as context), emits an
  event, and **drops that chunk's audio permanently** — never re-transcribing
  finalized speech.
- Emits a **two-tier event** (`committed` + `transient`) so any consumer — the
  harp CLI, or an external app like magpie in AInBox rendering a live meeting
  note — decides how to present it.
- Produces the **complete final text almost immediately** on finalization,
  because finalized chunks are already committed; only the small residual tail
  needs a last decode.

Cost is bounded by the maximum active-segment length, which is the real-time
guarantee.

## Non-goals (this design)

- Live keystroke typing of finalized chunks (a future sink; if built, types
  finalized text only — never backspaces).
- Per-host empirical tuning of intervals on a mic-equipped machine (tracked
  separately in `TASKS.md`).
- macOS / portability work.

## Architecture

The engine is the deliverable. Sinks (clipboard, terminal, file, external
consumers) are just consumers of the event stream.

### 1. Event contract — `src/harp/events.py`

Replace `CommitEvent(text, words, ts)` with a two-tier event:

```python
@dataclass(frozen=True)
class TranscriptEvent:
    committed: str    # cumulative finalized text — append-only, never revised
    transient: str    # hypothesis of the in-progress segment — may change/vanish
    is_final: bool     # True only on the end-of-session flush
    ts: float

    @property
    def text(self) -> str:                       # back-compat for existing sinks
        return f"{self.committed} {self.transient}".strip()
```

`committed` is monotonic and append-only. `transient` is the current best
guess of the not-yet-finalized segment and may be rewritten or emptied between
events. The `text` property preserves the old "full prefix" shape so
`TerminalDisplay` and the clipboard sink keep working during migration.

### 2. Engine — `src/harp/streaming.py` (pure, I/O-free)

Rewrite `StreamingTranscriber` as a VAD-segmented transcriber. It stays
dependency-injected — it receives a `transcribe` callable **and** a `vad`
object — so it is fully testable with fakes, no model load.

State:
- `committed: str`
- `active_buf: np.ndarray` — audio since the last finalized boundary
- `t_total: float` — total audio seconds fed

`feed(pcm)` appends to `active_buf` and advances `t_total`.

`step() -> TranscriptState` decides, in order:

1. **Warm-up** (`t_total < warmup`, default ~10s): accumulate only. Emit
   `transient` = a single decode of the current buffer (today's speculative
   behavior). **No finalization, no drop** — a short utterance that ends here
   becomes one clean decode via `finalize()`.
2. **Past warm-up — VAD boundary:** run the injected `vad` on `active_buf`.
   If a **trailing silence ≥ `silence_threshold`** follows the last speech
   segment, finalize at that boundary: decode `active_buf` up to the boundary
   **once** with `committed[-200:]` as `initial_prompt`, append to
   `committed`, **drop** the consumed audio from `active_buf` (keep the
   trailing silence + any new speech), return a state whose `transient` is
   reset.
3. **Force-cut:** if `active_buf` length > `max_segment` (~25s) with no pause,
   finalize at the last word boundary (using word timestamps from the decode),
   drop, continue. This bounds cost when someone speaks without pausing.
4. **Otherwise:** re-decode the **bounded** `active_buf` → `transient` preview.

`finalize() -> TranscriptState` decodes the residual `active_buf` once,
appends to `committed`, returns the final state with empty `transient` and
`is_final` semantics. Because finalized chunks were already committed+dropped,
the complete text is ready with at most one short decode of latency.

**Cost model:** at any instant the engine re-decodes at most `max_segment`
seconds (the active segment). Finalized audio is dropped and never re-decoded.
This is the real-time guarantee. Re-decoding the *un-finalized* active segment
for the transient preview is allowed and bounded — it does not violate "never
re-transcribe finalized chunks."

`TranscriptState` keeps its current shape (`committed`, `tail`/`transient`,
`full`); rename `tail` → `transient` for consistency with the event.

### 3. VAD wrapper — `src/harp/vad.py` (new)

A thin wrapper over Silero VAD, already bundled with `faster-whisper`
(`faster_whisper.vad.get_vad_model`, `get_speech_timestamps`, `VadOptions`).
Given `active_buf` (float32 16 kHz), return speech segments so the engine can
detect a trailing-silence boundary. Silero is tiny and runs far faster than
real-time, so re-running it on the bounded active buffer each step is cheap.

A small protocol keeps the engine decoupled and testable:

```python
class SpeechDetector(Protocol):
    def speech_segments(self, audio: np.ndarray) -> list[tuple[int, int]]: ...
```

`SileroDetector` is the production implementation. If the Silero model fails
to load, the engine falls back to **time-based force-cuts at `max_segment`**
(no VAD) so it still streams — degraded boundary quality, not a hard failure.

### 4. Audio source — `src/harp/audio.py`

Add `FileSource(path)` implementing the existing `AudioSource` Protocol:
decode any `ffmpeg`-readable file (`.wav`, `.m4a`, `.mp3`, ...) to 16 kHz mono
int16 frames and yield them in fixed-size chunks (as fast as decode allows).
`MicrophoneSource` is untouched. Decoding reuses faster-whisper's bundled
audio loading (`faster_whisper.audio.decode_audio`) where possible to avoid a
new dependency.

### 5. Session + CLI

- `HarpSession` (`src/harp/session.py`) drives the new engine and yields
  `TranscriptEvent`s. Same threading model (worker feeds frames + steps on the
  slide cadence; consumer drains a queue). The warm-up→chunked transition is
  internal to the engine; the session is unaware.
- New CLI verb `harp transcribe <file>` (`src/harp/cli/main.py`): build a
  `FileSource`, run a session, print `committed` "in the dark" (bold/normal)
  and `transient` "in the light" (dim). This is the thin end-to-end proof and
  is deterministically testable without a mic.
- Existing `harp start` hotkey daemon keeps clipboard-paste for short
  dictation and gets rewired to the new engine in Slice 2.

### 6. Config — `src/harp/config.py`

Add:
- `stream_warmup: float = 10.0` — seconds before entering chunked mode.
- `stream_silence_threshold: float = 0.5` — trailing silence (s) that triggers
  a chunk boundary.
- `stream_max_segment: float = 25.0` — force-cut length (s).
- `stream_vad: bool = True` — enable Silero VAD (off → time-based force-cuts).

Retire `stream_window` and `stream_overlap` (subsumed by `max_segment`). Keep
`stream_slide_interval` as the transient-preview cadence. Update `.harp.yaml`
generation (`harp init`) and `harp config` output accordingly.

## Error handling

- **VAD load failure** → time-based force-cut fallback; engine still streams.
- **Decode exceptions** → worker swallows and keeps the last `committed`
  (current behavior); compute-type / CUDA fallback already lives in
  `LocalWhisperEngine.transcribe`.
- **Empty / silence-only audio** → no committed text; `finalize()` returns an
  empty final state.
- **FileSource on a missing/unreadable file** → raise a clear error before the
  session starts.

## Testing (inline — never delegated)

- **Pure-engine tests** with a fake `transcribe` (scripted text keyed by
  buffer length/content) and a fake `SpeechDetector` (scripted speech/silence):
  - finalized audio is dropped — assert `transcribe` only ever sees bounded
    buffers (it never re-sees a finalized chunk's samples);
  - `committed` is append-only across the event stream;
  - warm-up: a short input yields a single decode and no premature chunk drop;
  - force-cut fires when the active segment exceeds `max_segment` with no
    silence;
  - boundary finalization moves the right prefix to `committed`.
- **`FileSource` integration** over a tiny fixture WAV → assert the
  `TranscriptEvent` stream and the final text.
- **VAD wrapper smoke test** on a short fixture (real Silero; mark slow if it
  loads a model).
- Existing display/clipboard tests updated for the `text` back-compat property.

## Vertical slices

Build the thinnest end-to-end path first, then widen.

- **Slice 1 — engine + file front-end (thinnest end-to-end path):**
  `TranscriptEvent`, VAD-segmented `StreamingTranscriber`, `vad.py`,
  `FileSource`, and `harp transcribe <file>` printing dark/dim. File-based so
  the whole engine is deterministically testable without a mic. Tests inline.
- **Slice 2 — mic/hotkey rewire:** point `harp start` at the new engine as the
  default streaming mode; keep the clipboard sink for short dictation.
- **Slice 3 — polish:** file-output sink (`-o transcript.md`), config docs,
  refresh stale `docs/design.md`, README, `docs/library.md`, CHANGELOG, and add
  the missing `AGENTS.md` + `know-how/` for the repo.

## Repo housekeeping (folded into Slice 3)

- Add `AGENTS.md` (the repo currently has none — workspace convention wants
  one) plus a `know-how/` entry documenting the streaming engine.
- Refresh `docs/design.md`, which still references the removed `HarpDaemon`,
  `AudioStreamer`, and command mode.
- Update the stale README (still advertises v0.6.0 / `--type`).

## Real-time performance (measured 2026-06-27, zion CPU)

The first end-to-end build was ~1.15x real-time (94s to process a 73s clip with
`base`, `beam_size=5`, `compute_type=default`→float32, transient preview on) —
it falls progressively behind a live meeting. Benchmarking isolated the cause:

- The Whisper model is **not** the bottleneck: a single batch decode of the 73s
  clip is RTF 0.28 (`base`/beam5/float32) down to RTF 0.14 (`base`/beam1/int8).
- The streaming loop did **~4x redundant decode work** by re-decoding the
  growing in-progress buffer on every transient-preview step, then again at
  finalization.

Resolution — the default streaming path is **finalize-only**:

- Each VAD chunk is decoded exactly once → decode work ≈ 1x audio → RTF ≈ batch
  RTF. Measured **24.7s for 73.1s (RTF ≈ 0.34, ~0.27 steady-state excl. model
  load) — ~3-4x faster than real-time**, so lag cannot accumulate.
- Streaming decodes default to `beam_size=1` (config `stream_beam_size`) and the
  CLI promotes `compute_type=default`→`int8` on CPU (~2x over float32).
- The live **transient preview is opt-in** (`stream_transient` / `--preview`),
  since re-decoding the in-progress chunk costs ~2-4x and is what blocks
  real-time on CPU. The two-tier `TranscriptEvent` contract is unchanged —
  `transient` is simply empty in finalize-only mode. Enable the preview when
  running a small model or on GPU, or for a live-typing UI.
- Side benefit: per-chunk decoding can transcribe quiet tails that a single
  long batch decode drops.

Latency notes: steady-state lag is eliminated by RTF « 1. Initial latency is
bounded by `stream_warmup` (default 10s) before the first chunk — lower it for
snappier first output on long-form sources at the cost of the short-dictation
"single clean decode" property.

## Open tuning questions (deferred to implementation/tuning, not blocking)

- Exact defaults for `warmup`, `silence_threshold`, `max_segment`, and the
  slide cadence per model/device — need a mic-equipped host for live tuning.
- Whether the transient preview should apply LocalAgreement-2 across passes to
  reduce display flicker, or just show the latest active-segment decode. Start
  with the latter (simpler); add stabilization only if flicker is visible.
