# Realtime latency: measured limits of the current engine (2026-07-29)

Grounding measurements for "how do we make harp really work for realtime
transcription". Everything below is measured, not inferred.

**Host:** zion — Intel i7-6820HQ (4c/8t Skylake, 2015), Quadro M2000M (Maxwell,
4 GB), 30 GB RAM. Governor `powersave`; cores sat at **~0.9–1.4 GHz** during the
runs (max 3.6). Treat absolute numbers as this-machine-specific; the *shape* of
the curves is architectural and portable.

**Clip:** `tests/assets/ground_truth.wav` — 73.1 s, 16 kHz mono, TTS-generated,
deliberately hard vocabulary ("quintessences", "syncopated", "ephemeral").
WER computed against `tests/assets/ground_truth.txt`, 200 reference words,
case/punctuation-insensitive.

Harness: `.playground/harp-realtime/` (`bench_harp.py`, `bench_window.py`,
`bench_moonshine.py`, `bench_matrix.py`, `bench_cuda.py`, `bench_tail.py`).

## Finding 1 — Whisper's decode cost is flat in buffer length

This is the decisive fact. Whisper's encoder always processes a **30 s-padded
mel**, so one decode call costs the same whether you hand it 1 second of audio
or 25.

CPU, int8, `beam_size=1`, best of 3 (ms per single `transcribe()` call):

| window | tiny | base | small |
|-------:|-----:|-----:|------:|
|  1 s | 2444 | 3173 |  9668 |
|  3 s | 1966 | 5298 |  9146 |
|  5 s | 2036 | 3379 |  9679 |
| 10 s | 1851 | 3295 | 11004 |
| 15 s | 2000 | 4683 | 11544 |
| 25 s | 2398 | 5310 | 12377 |
| 30 s | 3490 | 5854 | 18403 |

25× the audio for ~1× the cost. **A whisper decode on this host has a fixed
floor of ~2.0 s (`tiny`) / ~3.3 s (`base`) / ~9.7 s (`small`).**

### Consequences

- **Sliding-window re-decode policies are unaffordable here.** LocalAgreement-2
  (`ufal/whisper_streaming`), AlignAtt/SimulStreaming (`ufal/SimulStreaming`)
  and WhisperLiveKit all work by re-decoding a growing buffer every
  `MinChunkSize` and committing an agreed prefix. Emitting a partial every
  second would need RTF 2–3.5 on `base`. The published whisper_streaming latency
  is **3.3 s** — and that's on hardware far better than this.
- **The current engine is already optimal for whisper's cost structure.**
  `StreamingTranscriber`'s finalize-once-and-drop pays the fixed cost exactly
  once per chunk; RTF 0.142 is that ~3.3 s amortized over a ~25 s chunk. There
  is no idle headroom to spend — cost is strictly linear in *decode count*.
- **Whisper cannot produce sub-second partials on this host, at any tuning.**
  Getting them requires a second model with a streaming (causal) encoder whose
  cost scales with the *increment*, not the buffer.

## Finding 2 — Baseline, whole-clip

| config | RTF | ×realtime | WER |
|---|---:|---:|---:|
| `base` int8 CPU (harp default) | **0.142** | 7.0× | **9.5 %** |
| `base` float32 CUDA | 0.279 | 3.6× | 11.5 % |
| `small` float32 CUDA | 0.597 | 1.7× | **3.5 %** |

## Finding 3 — No GPU path on this laptop

CTranslate2 4.7.1 sees the Quadro M2000M but Maxwell (cc 5.0) supports
**float32 only** — no int8, no fp16:

```
get_supported_compute_types('cpu')  -> {int8, int8_float32, int16, float32}
get_supported_compute_types('cuda') -> {float32}
```

Result: `base` on the GPU (RTF 0.279) is **2× slower than the CPU** (0.142).
The fixed-cost floor gets *worse*, not better (4.4 s vs 3.3 s per call). Don't
plumb a CUDA path for latency on this class of hardware.

Worth noting separately: `small` on CUDA reaches **WER 3.5 %** — a large quality
win over `base` (9.5 %) at 1.7× realtime. Relevant for batch/quality modes, not
for latency.

## Finding 4 — Moonshine v2 streaming: right cost structure, wrong numbers here

`moonshine-voice` 0.1.0 (MIT, 56 MB wheel, bundled ONNX runtime — deps are only
numpy / sounddevice / requests / tqdm / filelock / platformdirs / google-crc32c;
**no torch, no onnxruntime pin**). Its encoder is causal with sliding-window
self-attention, so per-update cost is **incremental**, not buffer-sized.

| model | `update_interval` | RTF | ×realtime | WER | 1st text @ | commit lag (med) | ms/update |
|---|---:|---:|---:|---:|---:|---:|---:|
| tiny-streaming  | 0.3 s | 1.456 | 0.7× | 38.5 % | 2.6 s | 0.47 s | 335 |
| tiny-streaming  | 0.5 s | 1.062 | 0.9× | 41.5 % | 2.6 s | 0.20 s | 300 |
| tiny-streaming  | 1.0 s | 0.607 | 1.6× | 44.0 % | 3.1 s | 0.53 s | 285 |
| small-streaming | 1.0 s | 1.207 | 0.8× | 19.0 % | 2.1 s | 0.53 s | 742 |
| small-streaming | 2.0 s | 0.818 | 1.2× | 18.0 % | 2.0 s | 0.91 s | 885 |

It delivers the **latency profile** it advertises (first text ~2 s, sub-second
commit lag, per-update cost independent of buffer length) but on this host the
accuracy is 2–4× worse than `base` and only `tiny@1.0` comfortably keeps up.
The paper's headline latencies (50/148/258 ms) are **Apple M3**.

API shape maps cleanly onto harp's event contract, which matters if it's ever
used as a preview tier: `TranscriptLine(text, start_time, duration, line_id,
is_complete, is_updated, has_text_changed, words: [WordTiming(word, start, end,
confidence)], last_transcription_latency_ms)`. Completed lines ≈ `committed`;
the open line ≈ `transient`. Word timings and per-update latency come free.

## Finding 5 — Tail latency is O(duration) today, and could be O(1)

"Tail latency" = wall time from stop-recording to final text. This is the metric
the dictation front-ends are judged on. `base` int8, `cpu_threads=4`:

| scenario | tail |
|---|---:|
| whole-clip at `stop()` — 10 s utterance | 3.39 s |
| whole-clip at `stop()` — 30 s utterance | 4.78 s |
| whole-clip at `stop()` — 73 s utterance | **12.51 s** |
| batched (`bs=8`) — 73 s utterance | 8.38 s |
| decode a 5 s tail only (streaming-finalized) | 4.66 s |
| decode an 8 s tail only (streaming-finalized) | 4.23 s |

Two things:

- **`DictationSession` — the mode all three consumers use (`aegis`, `alia`,
  `warden`) — is the O(duration) path.** It buffers the whole clip and decodes
  it at `stop()`, so tail grows with utterance length: 3.4 s → 4.8 s → 12.5 s.
  If finalization happened during the pauses instead (which
  `StreamingTranscriber` already does), the tail would be one bounded decode —
  **O(1), ~3.5–4.5 s here** — regardless of how long the user spoke.
- **`BatchedInferencePipeline` (faster-whisper 1.2.1) helps only multi-window
  tails**: 12.51 s → 8.38 s on the 73 s clip (~1.5×), but neutral-to-worse at
  10 s and 30 s (a single 30 s window has nothing to batch). Small quality cost:
  WER 8.5 % sequential → 10.0 % batched.

### Caveat on these numbers

This host throttles hard and the run-to-run variance is large (the same ~2 s
decode measured 3.6 s and 8.4 s in different blocks). Trust the *scaling shape*,
not the absolute values. In particular, `cpu_threads=8` (logical) measured worse
than `cpu_threads=4` (physical) on **every** row — plausible, since there are 4
physical cores, but the 8-thread block ran second, so thermal drift is a
confound. **Needs an A/B/A re-run before acting on it.**

## What the field actually does (survey)

- **`ufal/whisper_streaming`** (Macháček et al., IJCNLP 2023) — LocalAgreement-2:
  re-decode the growing buffer, commit the longest common prefix of two
  consecutive hypotheses; trim the buffer at sentence boundaries using
  timestamps. Measured latency **3.3 s** (EN). Cost = N re-decodes.
- **`ufal/SimulStreaming`** (IWSLT 2025 winner, MIT) — AlignAtt policy: use the
  decoder's cross-attention to detect when attention enters a "dangerous zone"
  near the buffer end, and stop emitting there. **~5× cheaper than
  whisper_streaming** because it needs one decoder pass, not two hypotheses.
  Knobs: `frame_threshold` (25), `beams`, `audio_max_len`, `never_fire`.
- **`QuentinFuxa/WhisperLiveKit`** — packages both policies (`--backend-policy
  simulstreaming|localagreement`) plus VAD/VAC, over faster-whisper / MLX /
  Voxtral / Qwen3-ASR backends.
- **Wispr Flow** — *not* a streaming-word product. Cloud pipeline, **700 ms p99
  end-to-end after you stop speaking**, ASR followed by a fine-tuned Llama
  transcript-enhancement pass on Baseten/TensorRT-LLM (100+ tokens in <250 ms).
  Its differentiator is the **LLM cleanup**, not ASR latency. No offline mode.
- **Streaming-native architectures** (cost scales with increment, not buffer):
  Moonshine v2, NVIDIA Parakeet TDT (RTFx >2000 on GPU), sherpa-onnx streaming
  Zipformer transducer (built for CPU realtime), Kyutai STT (delayed streams,
  0.5 s delay, CC-BY-4.0 weights, GPU-oriented).

## Open probes

Three things were not measured and should be before designing around them:

1. **Streaming-path WER vs whole-clip WER.** Finalize-during-recording decodes
   chunks without full-utterance context; the overlap-holdback machinery is
   meant to absorb that, but the cost is unmeasured. This gates making the
   streaming path the default for dictation.
2. **`cpu_threads` = physical vs logical cores**, A/B/A to remove thermal drift.
3. **sherpa-onnx streaming Zipformer** was not benchmarked and is the most
promising untested candidate for a cheap preview tier: a true streaming
transducer, designed for CPU realtime, Python bindings, much smaller than
Moonshine small. Measure it the same way before designing around it.

## Sources

- [Turning Whisper into Real-Time Transcription System (arXiv 2307.14743)](https://arxiv.org/abs/2307.14743)
- [ufal/whisper_streaming](https://github.com/ufal/whisper_streaming)
- [ufal/SimulStreaming](https://github.com/ufal/SimulStreaming)
- [QuentinFuxa/WhisperLiveKit](https://github.com/QuentinFuxa/WhisperLiveKit)
- [Moonshine v2 (arXiv 2602.12241)](https://arxiv.org/abs/2602.12241v1)
- [moonshine-ai/moonshine](https://github.com/moonshine-ai/moonshine)
- [Wispr Flow on Baseten](https://www.baseten.co/resources/customers/wispr-flow/)
- [kyutai-labs/delayed-streams-modeling](https://github.com/kyutai-labs/delayed-streams-modeling)
- [k2-fsa/sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)
