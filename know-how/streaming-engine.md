# Know-how: the streaming transcription engine

**When to reach for this:** changing transcription behaviour, latency, chunk
boundaries, or real-time performance; adding a new `AudioSource` or
`SpeechDetector`; debugging "it lags behind"/"it hallucinates"/"text appears
late".

## The mental model

Audio flows `AudioSource → HarpSession → StreamingTranscriber`, which emits
`TranscriptEvent(committed, transient, is_final, ts)`. `committed` is
append-only; `transient` is the in-progress guess.

The engine has two phases:

1. **Warm-up** (`< warmup` seconds fed, default 10): just buffer. A short
   utterance that ends here is one clean decode at `finalize()` — preserves
   classic push-to-talk dictation quality.
2. **Chunked streaming**: each `step()` runs the VAD on the *active buffer*
   (audio since the last boundary). On a **trailing silence ≥
   `silence_threshold`** it finalizes the chunk: decode once → append to
   `committed` → **drop the audio**. A chunk past `max_segment` with no pause is
   force-cut.

## Why it's real-time (and how to keep it that way)

The model is not the bottleneck — a batch decode is RTF ~0.14–0.28 on
`base`/CPU. The cost is **redundant re-decoding**. Two rules keep it real-time:

- **Finalized audio is dropped, never re-decoded.** Per-step cost is bounded by
  `max_segment`. Don't add anything that re-reads committed audio.
- **The transient preview is the expensive part** (re-decodes the in-progress
  chunk every step, ~2–4× cost). It's **opt-in** (`transient=False` default /
  `--preview`). Finalize-only ⇒ decode work ≈ 1× audio ⇒ RTF ≈ batch RTF
  (measured ≈0.34, ~3–4× faster than real-time, so lag can't accumulate).

Fast-decode defaults: the CLI promotes `compute_type=default`→`int8` on CPU
(~2×) and streaming uses `beam_size=1` (`stream_beam_size`). Both live in
`_build_engine` (`cli/main.py`) — shared by `start` and `transcribe`.

## The cadence gotcha (don't regress this)

`HarpSession` drives `step()` by **audio-time fed, not wall-clock**. A
`FileSource` delivers audio far faster than real-time; a wall-clock gate lets
the whole file arrive before the first step, collapsing the stream into a single
batch decode (was a real bug — see commit history). If you touch `_run`, keep
the sample-counting cadence.

## Tuning knobs (config / CLI)

- `stream_warmup` — initial latency before the first chunk vs short-dictation
  single-decode. Lower (~3s) for snappier long-form first output.
- `stream_silence_threshold` — how long a pause must be to cut a chunk.
- `stream_max_segment` — force-cut bound for pause-less speech.
- `stream_beam_size` — 1 (fast) … 5 (best quality, short clips).
- `stream_transient` / `--preview` — live preview (not real-time on CPU `base`).

## Overlap finalization (don't regress this)

Fixed-window force-cuts land mid-word. Decoding that cold tail/onset garbles
weak models and corrupts the seam. So `_commit_segments` (used when a
`transcribe_segments` decoder is injected):

- commits by **absolute audio time** (`_committed_abs`), skipping anything
  already committed — exact overlap dedup, no fuzzy text matching;
- **holds back** the trailing `overlap` seconds of a non-mid-stream chunk (cut
  mid-word, unreliable) so the next chunk re-decodes it with full context;
- retains exactly the uncommitted audio (`_committed_abs` onward) as lead-in;
- has a forward-progress fallback: if holdback commits nothing (one giant
  segment), it commits without holdback so the buffer can't stall.

The string path (`transcribe` only, no segments) keeps the old drop-the-whole-
prefix behaviour for back-compat and the transient preview.

## AudioSource.close() must drain, not abort (don't regress this)

An `AudioSource`'s `close()` means **"no more *new* input — emit what's already
captured, then end,"** NOT "abort now." A consumer may call `close()` and keep
draining `frames()`; abandoning buffered/decoded audio at that point clips the
tail. Both bundled sources follow this:

- `MicrophoneSource.close()` enqueues a `None` sentinel *after* the last
  captured frame; `_iter_frames` drains to the sentinel (not `while not
  _closed`) so the final push-to-talk utterance survives.
- `FileSource` decodes the whole file eagerly in `frames()`, then yields the
  blocks *without* bailing on `_closed` — the clip drains to completion.

Why it matters: `DictationSession.stop()` closes the source **before** joining
its decode worker. A `close()` that aborted mid-iteration (FileSource once did)
raced the worker to an **empty transcript** for the blessed
`DictationSession(FileSource(path)).start()/.stop()` recipe. Fixed 2026-07-03
(harpio 0.10.1); regression tests in `tests/test_audio_file.py` and
`tests/test_dictation.py`. Any new `AudioSource` must drain on close too.

## Known sharp edges

- **Weak-model hallucination**: `tiny` can still emit sporadic repetition
  bursts (repeated CJK tokens) on isolated chunks — an intrinsic limit of the
  model, not the chunking. The overlap fix + a compression-ratio > 2.4 segment
  filter (`whisper.transcribe_segments`) removed the katakana-everywhere case
  and made `base` robust, but `tiny` is not fully tamable. Recommend `base`+
  for production; `tiny` for latency-critical, error-tolerant use.
- The `initial_prompt` is `committed[-200:]`; it aids continuity. Observed
  robust on `base`.

## Testing

- Pure-engine tests use a fake `transcribe` (records buffer sizes) + a scripted
  `SpeechDetector` — assert append-only `committed`, audio dropped (bounded
  buffers), force-cut, warm-up behaviour. See `tests/test_streaming.py`.
- Real end-to-end: `tests/test_integration_stream.py` (marked `slow`) runs the
  full stack on `tests/assets/ground_truth.wav` with `base`.
