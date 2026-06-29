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

## Known sharp edges

- **Small-model hallucination on short/quiet chunks**: `tiny` emits repeated
  non-English tokens (e.g. katakana) on near-silence VAD chunks. `base` is
  unaffected. Mitigation (open): skip sub-threshold-speech chunks or check
  `no_speech_prob` before committing a decode.
- The `initial_prompt` is `committed[-200:]`; it aids continuity but a bad chunk
  could in principle bias the next one. Observed robust on `base`.

## Testing

- Pure-engine tests use a fake `transcribe` (records buffer sizes) + a scripted
  `SpeechDetector` — assert append-only `committed`, audio dropped (bounded
  buffers), force-cut, warm-up behaviour. See `tests/test_streaming.py`.
- Real end-to-end: `tests/test_integration_stream.py` (marked `slow`) runs the
  full stack on `tests/assets/ground_truth.wav` with `base`.
